import asyncio
import re
from pathlib import Path

from fastapi import APIRouter

from schemas.generate import GeneratedScript, GenerateResponse, StoryRequest, TestCase
from services.dom_scanner import DomScannerService
from services.flow_resolver import FlowResolverService
from services.llm import get_llm_client
from services.progress import progress_tracker
from services.script_executor import executor_service
from services.test_case_generator import TestCaseGeneratorService
from services.test_script_generator import TestScriptGeneratorService

router = APIRouter()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "generated_scripts"


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "test_case"


@router.get("/generate-progress")
async def generate_progress() -> dict:
    """Polled by the frontend while a /generate-tests request is in flight."""
    return progress_tracker.get()


@router.post("/generate-tests", response_model=GenerateResponse)
async def generate_tests(request: StoryRequest) -> GenerateResponse:
    # Blocking work (LLM calls, pytest dry-runs) is pushed to worker threads
    # with asyncio.to_thread so the event loop stays free to answer
    # /generate-progress polls; otherwise the progress endpoint would stall
    # until the whole pipeline finished.
    try:
        llm_client = get_llm_client()

        flow_resolver = FlowResolverService(llm_client)
        dom_scanner = DomScannerService()
        test_case_generator = TestCaseGeneratorService(llm_client)
        test_script_generator = TestScriptGeneratorService(llm_client)

        progress_tracker.set("resolving_flow", "Resolving the story into a navigable flow…")
        flow_steps = await asyncio.to_thread(flow_resolver.resolve, request.url, request.story)

        progress_tracker.set("scanning_dom", "Scanning the live site for real selectors…")
        element_map, scan_warnings = await dom_scanner.scan(request.url, flow_steps)

        progress_tracker.set(
            "generating_cases",
            f"Drafting test cases from the story ({len(element_map)} real elements captured)…",
        )
        raw_test_cases = await asyncio.to_thread(
            test_case_generator.generate, request.story, element_map
        )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        total = len(raw_test_cases)
        scripts: list[GeneratedScript] = []
        for i, raw_test_case in enumerate(raw_test_cases, start=1):
            test_case = TestCase(**raw_test_case)
            file_name = f"test_{_slugify(test_case.title)}.py"
            file_path = OUTPUT_DIR / file_name

            code, status, failure_detail = await asyncio.to_thread(
                _generate_verified_script,
                test_script_generator,
                raw_test_case,
                request.url,
                element_map,
                file_path,
                i,
                total,
            )

            script_id = executor_service.register(file_path, test_case.title)
            scripts.append(
                GeneratedScript(
                    test_case=test_case,
                    script_id=script_id,
                    file_name=file_name,
                    code=code,
                    status=status,
                    failure_detail=failure_detail,
                )
            )

        progress_tracker.set("done", "All scripts generated and verified.", total, total)
        return GenerateResponse(scripts=scripts, scan_warnings=scan_warnings)
    except Exception:
        progress_tracker.set("idle", "")
        raise


def _generate_verified_script(
    test_script_generator: TestScriptGeneratorService,
    raw_test_case: dict,
    url: str,
    element_map: list[dict],
    file_path: Path,
    index: int,
    total: int,
) -> tuple[str, str, str | None]:
    """Generate -> dry-run -> auto-repair once -> re-verify.

    Nothing is returned to the caller unverified: every script is executed
    headless at generation time, and a failing script gets one repair pass
    with its real failure output fed back to the model. Returns
    (code, status, failure_detail).
    """
    title = raw_test_case.get("title", "test case")

    progress_tracker.set(
        "generating_script", f"Writing script {index}/{total}: {title}", index, total
    )
    try:
        code = test_script_generator.generate(raw_test_case, url, element_map)
    except ValueError as e:
        file_path.write_text("", encoding="utf-8")
        return "", "error", str(e)[:2000]

    file_path.write_text(code, encoding="utf-8")
    progress_tracker.set(
        "verifying_script",
        f"Verifying script {index}/{total} in a real browser: {title}",
        index,
        total,
    )
    status, failure_detail = executor_service.dry_run(file_path)
    if status == "passed":
        return code, "verified", None

    progress_tracker.set(
        "repairing_script",
        f"Script {index}/{total} failed live verification - auto-repairing from the failure trace…",
        index,
        total,
    )
    try:
        repaired = test_script_generator.repair(
            raw_test_case, url, element_map, code, failure_detail or "unknown failure"
        )
    except ValueError as e:
        return code, "failed", (failure_detail or str(e))[:2000]

    file_path.write_text(repaired, encoding="utf-8")
    progress_tracker.set(
        "verifying_script",
        f"Re-verifying repaired script {index}/{total} in a real browser…",
        index,
        total,
    )
    status, failure_detail = executor_service.dry_run(file_path)
    if status == "passed":
        return repaired, "verified", None
    return repaired, "failed", (failure_detail or "dry run failed after repair")[:2000]

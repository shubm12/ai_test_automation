import re
from pathlib import Path

from fastapi import APIRouter

from schemas.generate import GeneratedScript, GenerateResponse, StoryRequest, TestCase
from services.dom_scanner import DomScannerService
from services.flow_resolver import FlowResolverService
from services.llm import get_llm_client
from services.script_executor import executor_service
from services.test_case_generator import TestCaseGeneratorService
from services.test_script_generator import TestScriptGeneratorService

router = APIRouter()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "generated_scripts"


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "test_case"


@router.post("/generate-tests", response_model=GenerateResponse)
async def generate_tests(request: StoryRequest) -> GenerateResponse:
    llm_client = get_llm_client()

    flow_resolver = FlowResolverService(llm_client)
    dom_scanner = DomScannerService()
    test_case_generator = TestCaseGeneratorService(llm_client)
    test_script_generator = TestScriptGeneratorService(llm_client)

    flow_steps = flow_resolver.resolve(request.url, request.story)
    element_map, scan_warnings = await dom_scanner.scan(request.url, flow_steps)
    raw_test_cases = test_case_generator.generate(request.story, element_map)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    scripts: list[GeneratedScript] = []
    for raw_test_case in raw_test_cases:
        test_case = TestCase(**raw_test_case)
        file_name = f"test_{_slugify(test_case.title)}.py"
        file_path = OUTPUT_DIR / file_name

        code, status, failure_detail = _generate_verified_script(
            test_script_generator, raw_test_case, request.url, element_map, file_path
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

    return GenerateResponse(scripts=scripts, scan_warnings=scan_warnings)


def _generate_verified_script(
    test_script_generator: TestScriptGeneratorService,
    raw_test_case: dict,
    url: str,
    element_map: list[dict],
    file_path: Path,
) -> tuple[str, str, str | None]:
    """Generate -> dry-run -> auto-repair once -> re-verify.

    Nothing is returned to the caller unverified: every script is executed
    headless at generation time, and a failing script gets one repair pass
    with its real failure output fed back to the model. Returns
    (code, status, failure_detail).
    """
    try:
        code = test_script_generator.generate(raw_test_case, url, element_map)
    except ValueError as e:
        file_path.write_text("", encoding="utf-8")
        return "", "error", str(e)[:2000]

    file_path.write_text(code, encoding="utf-8")
    status, failure_detail = executor_service.dry_run(file_path)
    if status == "passed":
        return code, "verified", None

    try:
        repaired = test_script_generator.repair(
            raw_test_case, url, element_map, code, failure_detail or "unknown failure"
        )
    except ValueError as e:
        return code, "failed", (failure_detail or str(e))[:2000]

    file_path.write_text(repaired, encoding="utf-8")
    status, failure_detail = executor_service.dry_run(file_path)
    if status == "passed":
        return repaired, "verified", None
    return repaired, "failed", (failure_detail or "dry run failed after repair")[:2000]

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
    element_map = await dom_scanner.scan(request.url, flow_steps)
    raw_test_cases = test_case_generator.generate(request.story)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    scripts: list[GeneratedScript] = []
    for raw_test_case in raw_test_cases:
        test_case = TestCase(**raw_test_case)
        code = test_script_generator.generate(raw_test_case, request.url, element_map)

        file_name = f"test_{_slugify(test_case.title)}.py"
        file_path = OUTPUT_DIR / file_name
        file_path.write_text(code, encoding="utf-8")

        script_id = executor_service.register(file_path, test_case.title)
        scripts.append(GeneratedScript(test_case=test_case, script_id=script_id, file_name=file_name))

    return GenerateResponse(scripts=scripts)

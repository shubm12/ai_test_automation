"""Stage 2 — Test case -> grounded Playwright code, one file per test case.

Hard rule, non-negotiable: the model may only use selectors present in the
provided element map. If a needed element isn't present, it must emit
`# SELECTOR_NOT_FOUND: <description>` instead of guessing. This is the core
anti-hallucination mechanism for the whole pipeline.
"""
import json

from services.llm import BaseLLMClient
from utils.validation import validate_and_retry

SYSTEM_PROMPT = """You write Python test code using pytest-playwright syntax.

You will be given:
1. A structured test case (title, steps, assertions, edge cases)
2. The target page URL
3. A JSON list of REAL elements that exist on the actual webpage(s), with their real selectors

STRICT RULES (do not break these):
- Always start the test with page.goto() using the EXACT page_url provided. Never use a relative path.
- You may ONLY use selectors that appear in the provided element list.
- Do NOT invent, guess, or assume any selector that isn't explicitly listed.
- If you need an element that is not present, insert a comment instead of a selector:
  # SELECTOR_NOT_FOUND: <description of what was needed>
- Write a single test function using the `page` fixture from pytest-playwright.
- The function must start with: def test_ and accept `page` as a parameter.
- Add `from playwright.sync_api import expect` at the top if you use `expect`.
- Respond with ONLY the Python code. No markdown fences, no explanation.
"""


class TestScriptGeneratorService:
    def __init__(self, llm_client: BaseLLMClient):
        self._llm = llm_client

    def generate(self, test_case: dict, url: str, element_map: list[dict]) -> str:
        slim_elements = self._slim_elements(element_map)
        user_prompt = f"""TEST CASE:
{json.dumps(test_case)}

PAGE URL:
{url}

REAL ELEMENTS (only use selectors from here):
{json.dumps(slim_elements)}
"""

        def _generate_once() -> str:
            raw = self._llm.complete(
                SYSTEM_PROMPT,
                user_prompt,
                json_mode=False,
                max_tokens=2048,
                temperature=0.2,
            )
            return self._strip_code_fences(raw)

        return validate_and_retry(_generate_once, max_retries=2)

    @staticmethod
    def _slim_elements(element_map: list[dict]) -> list[dict]:
        """Only the fields the prompt actually needs - the full scan payload
        (tag/id/testId/name/type/placeholder/ariaLabel/...) is several times
        larger and was pushing single requests over Groq's free-tier TPM cap."""
        slim = []
        for el in element_map:
            text = (el.get("text") or "")[:60]
            slim.append(
                {
                    "page": el.get("page"),
                    "text": text,
                    "selector": el.get("recommended_selector"),
                }
            )
        return slim

    @staticmethod
    def _strip_code_fences(code: str) -> str:
        code = code.strip()
        if code.startswith("```"):
            code = code.split("```")[1]
            if code.lower().startswith("python"):
                code = code[6:]
        return code.strip()

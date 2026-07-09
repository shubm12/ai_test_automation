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
- Immediately after page.goto(), add: page.set_default_timeout(5000)
  so a wrong assumption fails in 5 seconds instead of stalling for Playwright's 30-second default.
- You may ONLY use selectors that appear in the provided element list.
- Do NOT invent, guess, or assume any selector that isn't explicitly listed.
- If you need an element that is not present, insert a comment instead of a selector:
  # SELECTOR_NOT_FOUND: <description of what was needed>
- Respect each element's "page" field: an element is only visible on the page/state it was observed
  on. Never interact with or assert an element from a page the test has not navigated to at that
  point in the flow. Do NOT assume an action navigates somewhere (e.g. adding an item does NOT open
  the cart). If a listed element can perform the needed navigation (e.g. a cart link), add that
  click step first; if no listed element reaches that page, emit # SELECTOR_NOT_FOUND instead.
- Page labels of the form "X_after_<action>" show the page state AFTER performing <action>. If an
  element from state "X" does not also appear in "X_after_<action>", it no longer exists once that
  action is performed - do not click or assert it again afterwards (e.g. if "Add to cart" is absent
  from the after-state and "Remove" appears instead, a second "Add to cart" click is impossible;
  interact with "Remove" or assert the state change instead).
- Use the MINIMUM number of clicks needed. Never insert a click the test case does not require.
  Clicking a link (tag "a") navigates to a NEW page whose elements are unknown unless the map has a
  page group for it - after clicking a link with no matching "..._after_..." group, you may not use
  ANY selector from the previous page, and you have no selectors for the new page, so the test is
  broken. If a needed element (e.g. an add-to-cart button) is directly available on the current
  page, use it there instead of navigating through a link first.
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

    def repair(
        self,
        test_case: dict,
        url: str,
        element_map: list[dict],
        failed_code: str,
        failure_detail: str,
    ) -> str:
        """Regenerate a script that failed its dry run, feeding the actual
        runtime failure back to the model as evidence. Live failure output is
        far more corrective than any abstract rule - it names the exact
        selector/assertion that broke against the real page."""
        slim_elements = self._slim_elements(element_map)
        user_prompt = f"""The following generated test FAILED when executed against the live page.
Fix it. The failure output tells you exactly what went wrong (e.g. a selector that never appeared,
an element that no longer exists at that point in the flow, or an assertion on the wrong page).
Remove or rework the failing interaction - all STRICT RULES still apply, including using ONLY
selectors from the element list.

TEST CASE:
{json.dumps(test_case)}

PAGE URL:
{url}

REAL ELEMENTS (only use selectors from here):
{json.dumps(slim_elements)}

FAILED CODE:
{failed_code}

FAILURE OUTPUT:
{failure_detail[:2000]}
"""

        def _repair_once() -> str:
            raw = self._llm.complete(
                SYSTEM_PROMPT,
                user_prompt,
                json_mode=False,
                max_tokens=2048,
                temperature=0.2,
            )
            return self._strip_code_fences(raw)

        return validate_and_retry(_repair_once, max_retries=1)

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
                    "tag": el.get("tag"),
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

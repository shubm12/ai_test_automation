"""Stage 1 — Story -> 4-5 distinct, structured test cases.

Grounded in the real app: the prompt includes a compact summary of the UI
elements observed by the DOM scan (Stage 0), and instructs the model to only
propose scenarios exercisable through those elements. This applies the same
anti-hallucination principle as Stage 2, one stage earlier - it stops the
model from padding the test set with generic e-commerce tropes (out-of-stock
items, quantity increments, session timeouts) the target app doesn't have.
"""
import json

from services.llm import BaseLLMClient

SYSTEM_PROMPT = """You convert a detailed, multi-sentence plain-English QA feature story into a set
of structured test cases.

You will be given:
1. The feature story.
2. A summary of the REAL UI elements observed on the live target application, grouped by page/state.

Analyze the story and generate between 4 and 5 distinct test cases covering the primary happy path
and meaningful negative/edge scenarios implied by the story. Do not just restate one flow multiple
times - each test case should be genuinely distinct (different inputs, different failure modes, or
different sub-flows).

GROUNDING RULES (do not break these):
- Every test case must be exercisable using ONLY the UI elements listed in the summary.
- Do NOT invent features the application does not show evidence of. If the element summary contains
  no stock indicator, do not write out-of-stock scenarios. If it contains no quantity field, do not
  write quantity-increment scenarios. If it contains no session/timeout element, do not write
  session-expiry scenarios.
- Negative scenarios must come from misusing the elements that DO exist (wrong/empty input into the
  listed fields, clicking listed buttons in unexpected orders, re-clicking, removing then re-adding),
  not from imagined functionality.
- Elements are only visible on the page/state they are listed under. A step or assertion may only
  use elements from the page the user would actually be on at that point in the flow. Do NOT assume
  an action navigates somewhere (e.g. that adding an item opens the cart) - to use another page's
  elements, first include the explicit navigation step that reaches that page (e.g. clicking the
  cart link), and only if such a navigation element is listed.
- Page groups named "X_after_<action>" show the page state AFTER performing <action>. If an element
  from state "X" is absent from "X_after_<action>", performing that action removes/replaces it - do
  not write steps that use it again afterwards. A "repeat the action" scenario (e.g. duplicate add)
  is only valid if the same element still exists in the after-state; otherwise, test the state
  change itself (e.g. the button becoming "Remove") instead.
- Use the MINIMUM steps needed. Do not add steps the scenario does not require. Clicking a link
  (tag "a") navigates to a new page - if no page group documents what is there, the elements on it
  are unknown, so do not send the user through such a link. If a needed element (e.g. an
  add-to-cart button) is directly available on the current page, use it there rather than
  navigating into an undocumented page first.

Respond ONLY with valid JSON. No markdown fences, no explanation, no preamble.

Use exactly this schema:
{
  "test_cases": [
    {
      "title": "short descriptive title",
      "preconditions": ["list of things that must be true before the test starts"],
      "steps": ["ordered list of user actions"],
      "assertions": ["ordered list of things to verify after each key step"],
      "edge_cases": ["related negative/edge scenarios worth testing separately"]
    }
  ]
}
"""


class TestCaseGeneratorService:
    def __init__(self, llm_client: BaseLLMClient):
        self._llm = llm_client

    def generate(self, story: str, element_map: list[dict]) -> list[dict]:
        user_prompt = f"""FEATURE STORY:
{story}

REAL UI ELEMENTS OBSERVED ON THE LIVE APPLICATION (grouped by page/state):
{json.dumps(self._summarize_elements(element_map))}
"""
        raw = self._llm.complete(
            SYSTEM_PROMPT,
            user_prompt,
            json_mode=True,
            max_tokens=2048,
            temperature=0.3,
        )
        data = json.loads(raw)
        return data["test_cases"]

    @staticmethod
    def _summarize_elements(element_map: list[dict]) -> dict[str, list[str]]:
        """Compact page -> ["tag: text-or-placeholder", ...] view. Stage 1 only
        needs to know what capabilities exist, not real selectors (those stay
        Stage 2's concern), and the compact form keeps the request small enough
        for Groq's free-tier TPM cap."""
        by_page: dict[str, list[str]] = {}
        for el in element_map:
            page = el.get("page", "unknown")
            label = (el.get("text") or el.get("placeholder") or el.get("ariaLabel") or "")[:60]
            if not label:
                continue
            entry = f'{el.get("tag", "element")}: {label}'
            page_entries = by_page.setdefault(page, [])
            if entry not in page_entries:
                page_entries.append(entry)
        return by_page

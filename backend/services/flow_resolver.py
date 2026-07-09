import json

from flows.definitions import FlowStep, find_preset
from services.llm import BaseLLMClient

FLOW_EXTRACTION_PROMPT = """You read a plain-English QA feature story and extract the ordered
sequence of navigation actions needed to reach every page/state the story touches, so an
automated tool can replay them before it looks at any real page.

Respond ONLY with a valid JSON object. No markdown fences, no explanation.

Use exactly this schema:
{
  "steps": [
    {"action": "navigate", "target": "<free-text description of the page reached, e.g. 'login page'>"},
    {"action": "fill", "field_hint": "<free-text description of the field, e.g. 'username'>", "value": "<value to type>"},
    {"action": "click", "target_hint": "<free-text description of the element to click, e.g. 'login button'>"}
  ]
}

Rules:
- The first step must be {"action": "navigate", "target": "landing page"}.
- Only include actions implied by the story (logins, form fills, button clicks, page transitions).
- Keep field_hint/target_hint short and generic (e.g. "username", "password", "add to cart button",
  "checkout button") so they can be matched against real page elements later - do not guess real
  selectors or ids.
- If the story implies visiting multiple pages (e.g. cart, checkout), include a "navigate" step
  for each transition.
"""


class FlowResolverService:
    def __init__(self, llm_client: BaseLLMClient):
        self._llm = llm_client

    def resolve(self, url: str, story: str) -> list[FlowStep]:
        """The story is the source of truth for the journey - it's expected to be
        detailed enough to describe every page/action involved (per project scope).
        A hardcoded FLOWS preset, if one matches the URL, is only a fallback for
        when the LLM extraction call fails - it must never silently override a
        more detailed story with a shorter canned flow."""
        try:
            steps = self._resolve_from_story(story)
            if steps:
                return steps
        except Exception:
            pass

        preset = find_preset(url)
        if preset is not None:
            return preset

        return [{"action": "navigate", "target": "landing page"}]

    def _resolve_from_story(self, story: str) -> list[FlowStep]:
        raw = self._llm.complete(
            FLOW_EXTRACTION_PROMPT,
            story,
            json_mode=True,
            max_tokens=2500,
            temperature=0.2,
        )
        data = json.loads(raw)
        steps = data.get("steps", [])
        if not steps:
            raise ValueError("LLM returned no flow steps")
        return steps

"""Stage 1 — Story -> 4-5 distinct, structured test cases."""
import json

from services.llm import BaseLLMClient

SYSTEM_PROMPT = """You convert a detailed, multi-sentence plain-English QA feature story into a set
of structured test cases.

Analyze the story and generate between 4 and 5 distinct test cases covering the primary happy path
and meaningful negative/edge scenarios implied by the story. Do not just restate one flow multiple
times - each test case should be genuinely distinct (different inputs, different failure modes, or
different sub-flows).

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

    def generate(self, story: str) -> list[dict]:
        raw = self._llm.complete(
            SYSTEM_PROMPT,
            story,
            json_mode=True,
            max_tokens=2048,
            temperature=0.3,
        )
        data = json.loads(raw)
        return data["test_cases"]

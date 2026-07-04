# Requirements-to-CodeEngine — Full Project Context

## What we're building
An AI copilot for a hackathon that takes a **detailed, multi-sentence plain-English
feature story** (similar to the provided requirement markdown docs — not a single
sentence) and produces, within seconds:

1. **4–5 distinct, structured, human-readable test cases** derived from that story —
   the primary happy path plus meaningful negative/edge scenarios.
2. **One ready-to-run Playwright test script per test case**, executable against a
   real target application.
3. **Live pass/fail execution results for every generated test**, not just one
   aggregate result.

No manual translation from requirements to test scripts. No missed edge cases.
No boilerplate.

## Hackathon scoring structure
- Working Prototype & Live Execution — **40%** (does the AI actually run against a live app?)
- Prompt Engineering & System Architecture — **30%** (robust instructions, hallucination protection, clean handoff to the testing framework)
- Real-World Business Impact — **20%** (could a real company drop this into their workflow?)
- UX & Presentation — **10%** (can a QA engineer trust and interpret the output?)

## Target demo application (but should support any url)
`https://www.saucedemo.com` — a public QA practice site chosen because its
login → cart → checkout flow matches the kind of journey described in typical
feature stories.

Known test credentials: username - `standard_user` / password - `secret_sauce`.

## Core problem this architecture solves
The single biggest failure mode for AI-generated test code is **hallucinated
selectors** — the LLM writing `page.click("#checkout-btn")` when the real button is
`button.checkout-button-v2`. This makes generated tests fail immediately and is
the main reason this class of project fails demos. The entire pipeline is designed
around preventing this.

---

## The pipeline (4 stages)

### Stage 0 — DOM Grounding
Before any code is generated, Playwright walks the real target app and extracts
every interactive element with a ranked real selector:
`data-testid` > `id` > `name` > visible text.

Pages like `/cart` or `/checkout` don't exist independently — they're only reachable
after performing real actions (login, add-to-cart, etc). So scanning is driven by
**pre-defined flows**: an ordered list of `{page_name, actions_to_reach_it}`, replayed
live by Playwright, scanning the DOM at each stop. Each extracted element is tagged
with which page it belongs to.

**Deliberate scope limit (not a shortcut to hide from judges):** the system cannot
discover an arbitrary user journey from a story alone. Flows must be pre-defined for
whichever journeys are being demoed (e.g. login, login+cart, full checkout).
General-purpose flow discovery is good "future work" framing, not hackathon scope.

### Stage 1 — Story → Multiple Structured Test Cases
An LLM call converts the detailed story into **4–5 distinct test cases**, not one.
Output schema:

```json
{
  "test_cases": [
    {
      "title": "short descriptive title",
      "preconditions": ["..."],
      "steps": ["ordered list of user actions"],
      "assertions": ["ordered list of things to verify"],
      "edge_cases": ["related negative/edge scenarios"]
    }
  ]
}
```

System prompt must explicitly instruct: *"Analyze the story and generate between
4 and 5 distinct test cases covering the primary happy path and meaningful
negative/edge scenarios implied by the story. Do not just restate one flow multiple
times — each test case should be genuinely distinct (different inputs, different
failure modes, or different sub-flows)."*



### Stage 2 — Test Case → Grounded Code (one file per test case)
For **each** of the 4–5 test cases, generate one Playwright test file — as a loop,
not one giant call asking for all 5 functions at once. Smaller, focused generations
are less prone to truncation. Reuse the same Stage 0 element map for every call.

Hard rule for every generation, non-negotiable: the model may **only** use selectors
present in the provided element map. If a needed element isn't present, it must emit
`# SELECTOR_NOT_FOUND: <description>` instead of guessing. This constraint is the
core anti-hallucination mechanism and the main "prompt engineering" talking point
for judges.

Each generated file is validated with `ast.parse()` before being saved — if it's not
syntactically valid Python (usually caused by output truncation), retry generation
for that specific test case (up to ~2 retries) rather than proceeding with broken code.

Save each file using a slug of its test case title, e.g. `test_login_valid.py`,
`test_login_invalid_password.py`, into `generated_tests/`.

### Stage 3 — Execute All, Report Per-Test-Case
Run `pytest` against the whole `generated_tests/` directory (not a single file), and
parse results **per individual test node**, not just one aggregate pass/fail. Response
shape:

```json
{
  "results": [
    {"title": "...", "file": "test_login_valid.py", "status": "passed"},
    {"title": "...", "file": "test_login_invalid_password.py", "status": "failed", "stderr": "..."}
  ]
}
```

This per-test-case breakdown is what makes "no missed edge cases" a demonstrable
claim rather than a slogan — worth emphasizing to judges.

---

## LLM provider and model
**Groq** qwen-32b for now but should be easily configurable so that we can easily change llm and provider
## Hard-won gotchas — do not regress these
- `gpt-oss-120b` does **not** support the `reasoning_format` parameter (that was a
  DeepSeek-R1-specific option). Use `include_reasoning=False` instead — without it,
  the model's `<think>...</think>` chain-of-thought leaks into and corrupts
  `message.content`.
- Always set a generous `max_completion_tokens`. Too low silently truncates output
  mid-expression, producing invalid Python — `SyntaxError: '(' was never closed` is
  exactly what that failure mode looks like.
- Always validate generated code with `ast.parse()` before writing/running it,
  retrying generation (not just re-parsing the same broken output) if it fails. This
  is a second, explicit anti-hallucination/anti-truncation safety layer, worth
  naming directly when presenting the architecture.
- `response_format={"type": "json_object"}` works fine on `gpt-oss-120b` for Stage 1's
  structured JSON output.
- If Playwright runs in a sandboxed/root environment, launch Chromium with
  `args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]` or it crashes
  with `TargetClosedError`.

## Tech stack
- Backend: FastAPI (Python), async throughout
- LLM: Groq  via the `groq` Python SDK (for now)
- Test grounding/execution: Playwright (Python), `pytest-playwright`
- Target app: SauceDemo (`https://www.saucedemo.com`)
- Frontend: minimal — plain HTML or lightweight React is enough; polish is only 10% of scoring

## Current status
All 4 stages have been individually validated in a prototyping notebook for the
**single-sentence, single-test-case** version of the pipeline — verified end-to-end
producing a passing live `pytest` run with zero hallucinated selectors for a login
flow. Code for that version is attached alongside this document.


# Requirements-to-CodeEngine

An AI copilot that turns a detailed, plain-English feature story into:

1. 4-5 distinct, structured test cases (happy path + meaningful negative/edge scenarios)
2. One ready-to-run Playwright test script per test case, grounded only in selectors that
   actually exist on the live target page (no hallucinated selectors)
3. Live pass/fail execution results per test case

See [CLAUDE.md](CLAUDE.md) for the full architecture writeup (pipeline stages, anti-hallucination
design, scoring rationale).

## Project layout

```
backend/            FastAPI app - see below to run
frontend/            (planned)
Untitled113.ipynb     original prototyping notebook - superseded by backend/, not tracked in git
```

## Running the backend

### 1. Set up the virtual environment

From the project root:

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
```

### 2. Install dependencies

```bash
pip install -r backend/requirements.txt
playwright install chromium
```

(`playwright install-deps chromium` is also needed on Linux, but not on Windows/macOS.)

### 3. Configure environment variables

```bash
cd backend
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux
```

Edit `backend/.env` and fill in a real key:

```
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_groq_api_key_here
```

To use a different LLM provider/model later, add a new `BaseLLMClient` subclass in
`backend/services/llm.py` and a branch in `get_llm_client()` - nothing else in the codebase
needs to change.

### 4. Run the server

From `backend/`:

```bash
python main.py
```

**Important:** run it this way, not `uvicorn main:app --reload`. On Windows, Playwright's async
API needs the Proactor event loop to spawn Chromium as a subprocess, and `main.py` sets that
policy at import time - but uvicorn's CLI form only imports `main.py` *after* it has already
created its (incompatible) event loop. Running `python main.py` guarantees the policy is set
before any loop exists. The tradeoff is no auto-reload on file changes; restart manually after
editing backend code.

The API is now available at `http://127.0.0.1:8000`, with interactive docs at
`http://127.0.0.1:8000/docs`.

## API

### `POST /generate-tests`

Request:
```json
{
  "story": "A user logs in with username 'standard_user' and password 'secret_sauce', adds an item to the cart, proceeds to checkout, enters their first name, last name, and zip code, and completes the purchase, verifying the order confirmation message is displayed.",
  "url": "https://www.saucedemo.com"
}
```

Response: 4-5 generated test cases, each with a `script_id` and the `.py` file saved under
`backend/output/generated_scripts/`.

Note: the story is the source of truth for the journey (login steps, cart, checkout, etc.) -
include any credentials or specific values the flow needs, since the scanner replays exactly
what the story describes before looking at the real page.

### `POST /execute-tests`

Request:
```json
{ "script_id": "<id returned from /generate-tests>" }
```

Runs that script with pytest (headed, slowed down so the run is visible) and returns its
pass/fail result.

## Known limitations (by design, see CLAUDE.md)

- The DOM scan only sees pages the resolved flow actually visits - it can't discover an
  arbitrary journey with no basis in the story.
- Test cases describing behavior the target site doesn't actually have (e.g. an out-of-stock
  item on a site where every item is in stock) will come back with `# SELECTOR_NOT_FOUND`
  placeholders instead of real assertions - this is the anti-hallucination guard working as
  intended, not a bug.

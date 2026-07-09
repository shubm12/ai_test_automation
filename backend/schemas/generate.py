from pydantic import BaseModel


class StoryRequest(BaseModel):
    story: str
    url: str


class TestCase(BaseModel):
    title: str
    preconditions: list[str]
    steps: list[str]
    assertions: list[str]
    edge_cases: list[str]


class GeneratedScript(BaseModel):
    test_case: TestCase
    script_id: str
    file_name: str
    code: str
    # "verified" = passed its headless dry run at generation time.
    # "failed" = still failing after one auto-repair attempt; failure_detail says why.
    # "error" = could not be generated/validated at all.
    status: str
    failure_detail: str | None = None


class GenerateResponse(BaseModel):
    scripts: list[GeneratedScript]
    # Flow steps whose hint matched nothing during the DOM scan - a non-empty
    # list means parts of the journey were never scanned (see dom_scanner).
    scan_warnings: list[str] = []

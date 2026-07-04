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


class GenerateResponse(BaseModel):
    scripts: list[GeneratedScript]

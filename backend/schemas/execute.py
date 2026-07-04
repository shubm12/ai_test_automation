from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    script_id: str


class ExecuteResult(BaseModel):
    title: str
    file: str
    status: str  # "passed" | "failed" | "error"
    stdout: str | None = None
    stderr: str | None = None

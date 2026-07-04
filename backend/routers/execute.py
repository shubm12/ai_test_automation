from fastapi import APIRouter, HTTPException

from schemas.execute import ExecuteRequest, ExecuteResult
from services.script_executor import executor_service

router = APIRouter()


@router.post("/execute-tests", response_model=ExecuteResult)
async def execute_tests(request: ExecuteRequest) -> ExecuteResult:
    try:
        return executor_service.run(request.script_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown script_id: {request.script_id}")

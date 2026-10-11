from fastapi import APIRouter, BackgroundTasks, Request

from ..schemas import FindingRequest, FindingResponse


router = APIRouter(prefix="/api", tags=["findings"])


@router.post("/findings", response_model=FindingResponse, status_code=202)
def create_finding(payload: FindingRequest, background_tasks: BackgroundTasks,
                   request: Request):
    workflow = request.app.state.workflow
    response = workflow.create_job(payload)
    background_tasks.add_task(workflow.plan, response["job_id"])
    return response

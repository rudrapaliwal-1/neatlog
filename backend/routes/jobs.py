from fastapi import APIRouter, Query, Request


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(request: Request, limit: int = Query(default=100, ge=1, le=100),
              offset: int = Query(default=0, ge=0)):
    return request.app.state.workflow.list_jobs(limit, offset)


@router.get("/{job_id}")
def get_job(job_id: str, request: Request):
    return request.app.state.workflow.get_job(job_id)


@router.get("/{job_id}/patch")
def get_patch(job_id: str, request: Request):
    return request.app.state.workflow.get_patch(job_id)


@router.get("/{job_id}/evidence")
def get_evidence(job_id: str, request: Request):
    return request.app.state.workflow.evidence(job_id)


@router.get("/{job_id}/events")
def get_events(job_id: str, request: Request):
    return request.app.state.workflow.events(job_id)

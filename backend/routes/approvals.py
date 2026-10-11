from fastapi import APIRouter, Header, Request

from ..schemas import ApprovalRequest


router = APIRouter(prefix="/api/jobs", tags=["approvals"])


@router.post("/{job_id}/approval")
def decide_approval(job_id: str, payload: ApprovalRequest, request: Request,
                    x_operator_token: str | None = Header(default=None)):
    return request.app.state.workflow.decide(job_id, payload, x_operator_token)

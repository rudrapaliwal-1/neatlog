from fastapi import APIRouter, Header, Request

from ..approvals import require_operator
from ..auth import identity_kind


router = APIRouter(prefix="/api/jobs", tags=["verification"])


@router.post("/{job_id}/verify")
def verify(job_id: str, request: Request,
           x_operator_token: str | None = Header(default=None)):
    if identity_kind.get() != "USER_SESSION":
        require_operator(request.app.state.workflow.settings, x_operator_token)
    return request.app.state.workflow.verify(job_id)

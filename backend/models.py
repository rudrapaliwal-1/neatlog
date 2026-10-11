"""Workflow states and transition rules."""

from enum import StrEnum


class Status(StrEnum):
    FINDING_RECEIVED = "FINDING_RECEIVED"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    VERIFIED = "VERIFIED"
    POLICY_REJECTED = "POLICY_REJECTED"
    USER_REJECTED = "USER_REJECTED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.FINDING_RECEIVED: frozenset({Status.PLANNING, Status.EXECUTION_ERROR}),
    Status.PLANNING: frozenset({Status.AWAITING_APPROVAL, Status.POLICY_REJECTED, Status.EXECUTION_ERROR}),
    Status.AWAITING_APPROVAL: frozenset({Status.VERIFYING, Status.USER_REJECTED, Status.EXECUTION_ERROR}),
    Status.VERIFYING: frozenset({Status.VERIFIED, Status.VERIFICATION_FAILED, Status.EXECUTION_ERROR}),
    Status.VERIFICATION_FAILED: frozenset({Status.PLANNING, Status.RETRY_EXHAUSTED}),
    Status.VERIFIED: frozenset(),
    Status.POLICY_REJECTED: frozenset(),
    Status.USER_REJECTED: frozenset(),
    Status.RETRY_EXHAUSTED: frozenset(),
    Status.EXECUTION_ERROR: frozenset(),
}


class WorkflowError(Exception):
    """A safe error that can be returned to API callers."""

    def __init__(self, message: str, http_status: int = 409, code: str = "WORKFLOW_ERROR"):
        super().__init__(message)
        self.http_status = http_status
        self.code = code

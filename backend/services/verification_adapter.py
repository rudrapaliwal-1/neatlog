"""Direct trusted verifier integration with an approval verifier callback."""

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ..config import Settings
from ..schemas import VerificationResult
from .agent_adapter import load_callable


@dataclass(frozen=True)
class VerificationRequest:
    job_id: str
    target_app_id: str
    patch_id: str
    patch_text: str
    patch_hash: str
    approval_id: str
    attempt: int
    source_revision: str
    verification_profile: str
    run_id: str
    project_id: str | None = None
    source_root: str | None = None


ApprovalVerifier = Callable[[str, str, str, str], bool]


class VerificationAdapter(Protocol):
    def verify_patch(self, request: VerificationRequest,
                     approval_verifier: ApprovalVerifier) -> VerificationResult: ...


class ConfiguredVerificationAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def verify_patch(self, request: VerificationRequest,
                     approval_verifier: ApprovalVerifier) -> VerificationResult:
        if not self.settings.verifier_callable:
            raise RuntimeError("verification integration is not configured")
        if not approval_verifier(request.job_id, request.patch_id,
                                 request.patch_hash, request.approval_id):
            raise RuntimeError("approval reference is invalid")
        result: Any = load_callable(self.settings.verifier_callable, "verification")(request, approval_verifier)
        parsed = VerificationResult.model_validate(result)
        parsed.validate_counts()
        return parsed

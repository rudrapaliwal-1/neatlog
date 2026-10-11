"""Local single-operator approval authentication and trusted lookup."""

from dataclasses import dataclass
import hmac
from typing import Protocol
import sqlite3

from .config import Settings
from .models import WorkflowError
from .policy import patch_hash as compute_patch_hash


def require_operator(settings: Settings, supplied_token: str | None) -> str:
    if not settings.operator_token:
        raise WorkflowError("local operator token is not configured", 503)
    if (not supplied_token or not supplied_token.isascii() or
            not hmac.compare_digest(supplied_token, settings.operator_token)):
        raise WorkflowError("operator authentication required", 401)
    return settings.operator_name


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    identity_kind: str
    is_individual: bool


class ApprovalIdentityProvider(Protocol):
    """Future OIDC adapter must authenticate and return a stable human subject."""

    def authenticate(self, credential: str | None) -> AuthenticatedPrincipal: ...


class DemoTokenIdentityProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def authenticate(self, credential: str | None) -> AuthenticatedPrincipal:
        require_operator(self.settings, credential)
        return AuthenticatedPrincipal(self.settings.operator_name, "DEMO_SHARED_TOKEN", False)


def approval_is_active(db: sqlite3.Connection, job_id: str, patch_id: str,
                       patch_hash: str, approval_id: str) -> bool:
    row = db.execute("""
        SELECT p.patch_text FROM approvals a
        JOIN patch_proposals p ON p.id = a.patch_id
        JOIN jobs j ON j.id = a.job_id
        JOIN job_bindings jb ON jb.job_id = j.id
        JOIN approval_bindings ab ON ab.approval_id = a.id
        WHERE a.id = ? AND a.job_id = ? AND a.patch_id = ? AND a.patch_hash = ?
          AND a.decision = 'APPROVE' AND p.patch_hash = ?
          AND a.attempt = p.attempt AND j.attempt = p.attempt AND j.id = p.job_id
          AND j.status = 'VERIFYING' AND ab.target_app_id = j.target_app_id
          AND ab.source_revision = jb.source_revision AND ab.identity_kind IN ('DEMO_SHARED_TOKEN', 'USER_SESSION')
    """, (approval_id, job_id, patch_id, patch_hash, patch_hash)).fetchone()
    if row is None:
        return False
    try:
        return compute_patch_hash(row["patch_text"]) == patch_hash
    except UnicodeEncodeError:
        return False

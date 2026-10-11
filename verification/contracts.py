"""Data contracts and schemas for SENTINEL-X Verification (Developer 3).

Coordinated with Dev 1 (FastAPI Orchestrator) and Dev 4 (LLM Reflection Module).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable


class VerificationStatus(str, Enum):
    """Evaluation status emitted by Layer 5 Verification."""
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    POLICY_REJECTED = "POLICY_REJECTED"


# Callable accepting (patch_hash: str, approval_id: str) -> bool
ApprovalVerifier = Union[
    Callable[[str, str], bool],
    Callable[[str, str], Awaitable[bool]],
]


@dataclass
class _BaseModel:
    """Provides dictionary and JSON serialization helpers."""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return self._serialize(data)

    def _serialize(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize(item) for item in obj]
        if isinstance(obj, Enum):
            return obj.value
        return obj


@dataclass
class VerificationRequest(_BaseModel):
    """Payload provided by Dev 1 Orchestrator to request patch verification."""
    job_id: str
    target_app_id: str = "bola-demo-v1"
    patch_text: str = ""
    patch_hash: str = ""
    approval_id: str = ""
    patch_id: str = ""
    source_revision: str = ""
    verification_profile: str = ""
    run_id: str = ""
    attempt: int = 0
    timeout_seconds: int = 30
    source_root: Optional[str] = None


@dataclass
class VerificationResult(_BaseModel):
    """Structured verdict output returned to Dev 1 Orchestrator."""
    job_id: str
    patch_hash: str
    status: str  # VERIFIED, VERIFICATION_FAILED, EXECUTION_ERROR, POLICY_REJECTED
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    failed_tests: List[str] = field(default_factory=list)
    test_results: List[Dict[str, str]] = field(default_factory=list)
    duration_ms: int = 0
    execution_error: Optional[str] = None
    run_id: Optional[str] = None
    patch_id: Optional[str] = None
    test_suite_id: Optional[str] = None
    tests_collected: Optional[int] = None
    collection_complete: Optional[bool] = None
    execution_completed: Optional[bool] = None

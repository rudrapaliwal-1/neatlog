"""Tests for Developer 3 Backend Compatibility Adapter (verification/adapter.py).

Verifies:
1. dev1 backend request schema adaptation.
2. 4-argument backend approval callback support.
3. Fail-closed rejection of unapproved / mismatched patches.
4. Translation of test statuses to PASSED, FAILED, EXECUTION_ERROR.
5. Strict adherence to backend VerificationResult schema and count validations.
6. Integration with backend's ConfiguredVerificationAdapter.
"""

import sys
from pathlib import Path
import pytest

from verification.adapter import verify_backend_patch, _adapt_approval_verifier
from verification.patch_validator import PatchValidator

# Add workspace root to sys.path if not present
workspace_root = str(Path(__file__).resolve().parent.parent.parent)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

# Try importing backend classes if backend codebase is available
try:
    from backend.services.verification_adapter import (
        VerificationRequest as BackendVerificationRequest,
        ConfiguredVerificationAdapter,
    )
    from backend.schemas import VerificationResult as BackendVerificationResult
    from backend.config import Settings
    HAS_BACKEND = True
except ImportError:
    HAS_BACKEND = False


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CORRECT_PATCH = (FIXTURES_DIR / "correct_patch.diff").read_text(encoding="utf-8")
INCOMPLETE_PATCH = (FIXTURES_DIR / "incomplete_patch.diff").read_text(encoding="utf-8")
VALID_PATCH = CORRECT_PATCH
PARTIAL_PATCH = INCOMPLETE_PATCH


class DummyBackendRequest:
    def __init__(self, job_id, target_app_id, patch_id, patch_text, patch_hash, approval_id):
        self.job_id = job_id
        self.target_app_id = target_app_id
        self.patch_id = patch_id
        self.patch_text = patch_text
        self.patch_hash = patch_hash
        self.approval_id = approval_id
        from backend.manifest import TARGET_MANIFEST
        verifier_root = Path(__file__).resolve().parent.parent
        self.attempt = 0
        self.source_revision = TARGET_MANIFEST.source_revision(
            verifier_root / "lab", verifier_root / "protected_tests")
        self.verification_profile = TARGET_MANIFEST.verification_profile
        self.run_id = "run-" + "1" * 32


def test_adapt_approval_verifier_4_args():
    calls = []

    def backend_approval(job_id, patch_id, patch_hash, approval_id):
        calls.append((job_id, patch_id, patch_hash, approval_id))
        return True

    adapted = _adapt_approval_verifier(
        backend_approval, "job-1", "patch-1", "sha256:abc", "appr-1"
    )
    assert adapted("sha256:abc", "appr-1") is True
    assert len(calls) == 1
    assert calls[0] == ("job-1", "patch-1", "sha256:abc", "appr-1")


def test_adapt_approval_verifier_2_args():
    calls = []

    def simple_approval(patch_hash, approval_id):
        calls.append((patch_hash, approval_id))
        return True

    adapted = _adapt_approval_verifier(
        simple_approval, "job-1", "patch-1", "sha256:abc", "appr-1"
    )
    assert adapted("sha256:abc", "appr-1") is True
    assert len(calls) == 1
    assert calls[0] == ("sha256:abc", "appr-1")


def test_verify_backend_patch_rejects_unapproved():
    req = DummyBackendRequest(
        job_id="job-test-1",
        target_app_id="bola-demo-v1",
        patch_id="patch-1",
        patch_text=VALID_PATCH,
        patch_hash="sha256:" + PatchValidator.compute_hash(VALID_PATCH),
        approval_id="appr-invalid",
    )

    def failing_approval(job_id, patch_id, patch_hash, approval_id):
        return False

    result = verify_backend_patch(req, failing_approval)
    assert result["status"] == "EXECUTION_ERROR"
    assert "Approval validation failed" in result["execution_error"]
    assert result["tests_total"] == 0
    assert result["tests_passed"] == 0
    assert result["tests_failed"] == 0


def test_verify_backend_patch_rejects_unauthorized_target():
    req = DummyBackendRequest(
        job_id="job-test-1",
        target_app_id="unauthorized-target-app",
        patch_id="patch-1",
        patch_text=VALID_PATCH,
        patch_hash="sha256:" + PatchValidator.compute_hash(VALID_PATCH),
        approval_id="appr-1",
    )

    def approval(job_id, patch_id, patch_hash, approval_id):
        return True

    result = verify_backend_patch(req, approval)
    assert result["status"] == "EXECUTION_ERROR"
    assert "unauthorized target_app_id" in result["execution_error"]


def test_verify_backend_patch_rejects_mismatched_hash():
    req = DummyBackendRequest(
        job_id="job-test-1",
        target_app_id="bola-demo-v1",
        patch_id="patch-1",
        patch_text=VALID_PATCH,
        patch_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        approval_id="appr-1",
    )

    def approval(job_id, patch_id, patch_hash, approval_id):
        return True

    result = verify_backend_patch(req, approval)
    assert result["status"] == "EXECUTION_ERROR"
    assert "Patch hash mismatch" in result["execution_error"]


@pytest.mark.docker
def test_verify_backend_patch_full_success_docker():
    raw_hash = PatchValidator.compute_hash(VALID_PATCH)
    p_hash = f"sha256:{raw_hash}"
    req = DummyBackendRequest(
        job_id="job-e2e-pass",
        target_app_id="bola-demo-v1",
        patch_id="patch-pass",
        patch_text=VALID_PATCH,
        patch_hash=p_hash,
        approval_id="approval-pass",
    )

    def backend_approval(job_id, patch_id, patch_hash, approval_id):
        return (
            job_id == "job-e2e-pass"
            and patch_id == "patch-pass"
            and patch_hash == p_hash
            and approval_id == "approval-pass"
        )

    result = verify_backend_patch(req, backend_approval)

    assert result["status"] == "PASSED"
    assert result["tests_total"] == 8
    assert result["tests_passed"] == 8
    assert result["tests_failed"] == 0
    assert result["failed_tests"] == []
    assert result["execution_error"] is None
    assert result["duration_ms"] > 0

    if HAS_BACKEND:
        parsed = BackendVerificationResult.model_validate(result)
        parsed.validate_counts()
        assert parsed.status == "PASSED"


@pytest.mark.docker
def test_verify_backend_patch_partial_failure_docker():
    raw_hash = PatchValidator.compute_hash(PARTIAL_PATCH)
    p_hash = f"sha256:{raw_hash}"
    req = DummyBackendRequest(
        job_id="job-e2e-fail",
        target_app_id="bola-demo-v1",
        patch_id="patch-fail",
        patch_text=PARTIAL_PATCH,
        patch_hash=p_hash,
        approval_id="approval-fail",
    )

    def backend_approval(job_id, patch_id, patch_hash, approval_id):
        return True

    result = verify_backend_patch(req, backend_approval)

    assert result["status"] == "FAILED"
    assert result["tests_total"] == 8
    assert result["tests_failed"] > 0
    assert len(result["failed_tests"]) > 0

    if HAS_BACKEND:
        parsed = BackendVerificationResult.model_validate(result)
        parsed.validate_counts()
        assert parsed.status == "FAILED"


@pytest.mark.docker
def test_configured_verification_adapter_integration():
    if not HAS_BACKEND:
        pytest.skip("backend package not present")

    from backend.manifest import TARGET_MANIFEST

    settings = Settings(
        database_path=Path("backend/sentinel.db"),
        source_root=Path("verification/lab"),
        protected_tests_root=Path("verification/protected_tests"),
        verifier_callable="verification.adapter:verify_backend_patch",
    )
    adapter = ConfiguredVerificationAdapter(settings)

    raw_hash = PatchValidator.compute_hash(VALID_PATCH)
    p_hash = f"sha256:{raw_hash}"
    req = BackendVerificationRequest(
        job_id="job-adapter-e2e",
        target_app_id="bola-demo-v1",
        patch_id="patch-adapter",
        patch_text=VALID_PATCH,
        patch_hash=p_hash,
        approval_id="approval-adapter",
        attempt=0,
        source_revision=TARGET_MANIFEST.source_revision(
            Path("verification/lab"), Path("verification/protected_tests")),
        verification_profile="bola-required-tests-v1",
        run_id="run-" + "2" * 32,
    )

    def approval_callback(job_id, patch_id, patch_hash, approval_id):
        return (
            job_id == "job-adapter-e2e"
            and patch_id == "patch-adapter"
            and patch_hash == p_hash
            and approval_id == "approval-adapter"
        )

    backend_res = adapter.verify_patch(req, approval_callback)
    assert isinstance(backend_res, BackendVerificationResult)
    assert backend_res.status == "PASSED"
    assert backend_res.tests_total == 8
    assert backend_res.tests_passed == 8
    assert backend_res.tests_failed == 0
    assert backend_res.execution_error is None

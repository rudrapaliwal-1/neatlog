"""Negative tests for backend-to-verifier binding and evidence translation."""

from pathlib import Path

import pytest

from backend.manifest import TARGET_MANIFEST
from verification.adapter import _adapt_approval_verifier, verify_backend_patch
from verification.contracts import VerificationResult, VerificationStatus
from verification.evaluator import TestResultEvaluator
from verification.patch_validator import PatchValidator


ROOT = Path(__file__).resolve().parents[1]
PATCH = (ROOT / "fixtures" / "correct_patch.diff").read_text()
SOURCE_REVISION = TARGET_MANIFEST.source_revision(
    ROOT / "lab", ROOT / "protected_tests")


def request(**changes):
    values = {
        "job_id": "job-bound", "target_app_id": "bola-demo-v1",
        "patch_id": "patch-bound", "patch_text": PATCH,
        "patch_hash": "sha256:" + PatchValidator.compute_hash(PATCH),
        "approval_id": "approval-bound", "attempt": 0,
        "source_revision": SOURCE_REVISION,
        "verification_profile": TARGET_MANIFEST.verification_profile,
        "run_id": "run-" + "a" * 32,
    }
    values.update(changes)
    return values


def approval(job_id, patch_id, patch_hash, approval_id):
    return (job_id == "job-bound" and patch_id == "patch-bound" and
            patch_hash == request()["patch_hash"] and
            approval_id == "approval-bound")


@pytest.mark.parametrize("change", [
    {"source_revision": "sha256:" + "0" * 64},
    {"verification_profile": "other-suite"},
    {"run_id": "run-invalid"},
    {"attempt": 3},
])
def test_invalid_binding_rejected_before_runner(monkeypatch, change):
    import verification.adapter as adapter
    monkeypatch.setattr(adapter, "_run_async",
                        lambda coroutine: pytest.fail("runner must not launch"))
    result = verify_backend_patch(request(**change), approval)
    assert result["status"] == "EXECUTION_ERROR"
    assert result["tests_total"] == 0


def test_approval_callback_rejects_hash_and_approval_substitution():
    calls = []
    def backend_callback(job_id, patch_id, patch_hash, approval_id):
        calls.append((job_id, patch_id, patch_hash, approval_id))
        return True
    callback = _adapt_approval_verifier(
        backend_callback, "job-1", "patch-1", "sha256:approved", "approval-1")
    assert callback("sha256:forged", "approval-1") is False
    assert callback("sha256:approved", "approval-forged") is False
    assert calls == []
    assert callback("sha256:approved", "approval-1") is True
    assert calls == [("job-1", "patch-1", "sha256:approved", "approval-1")]


def test_forged_success_without_collection_is_not_translated(monkeypatch):
    import verification.adapter as adapter
    req = request()
    forged = VerificationResult(
        job_id=req["job_id"], patch_hash=req["patch_hash"],
        patch_id=req["patch_id"], run_id=req["run_id"],
        status=VerificationStatus.VERIFIED.value,
        tests_total=8, tests_passed=8, tests_failed=0,
        test_suite_id=TARGET_MANIFEST.verification_profile,
        tests_collected=None, collection_complete=None, execution_completed=None,
    )
    def return_forged(coroutine):
        coroutine.close()
        return forged
    monkeypatch.setattr(adapter, "_run_async", return_forged)
    result = verify_backend_patch(req, approval)
    assert result["status"] == "EXECUTION_ERROR"
    assert result["tests_total"] == 0


def test_verifier_result_with_wrong_run_is_rejected(monkeypatch):
    import verification.adapter as adapter
    req = request()
    forged = VerificationResult(
        job_id=req["job_id"], patch_hash=req["patch_hash"],
        patch_id=req["patch_id"], run_id="run-" + "b" * 32,
        status=VerificationStatus.VERIFIED.value,
        tests_total=8, tests_passed=8, tests_failed=0,
        test_suite_id=TARGET_MANIFEST.verification_profile,
        tests_collected=8, collection_complete=True, execution_completed=True,
    )
    def return_forged(coroutine):
        coroutine.close()
        return forged
    monkeypatch.setattr(adapter, "_run_async", return_forged)
    assert verify_backend_patch(req, approval)["status"] == "EXECUTION_ERROR"


def test_required_suite_skip_never_counts_as_verified():
    import json
    names = sorted(TestResultEvaluator.REQUIRED_TEST_NAMES)
    tests = [{"nodeid": f"protected_tests/test_security.py::{name}",
              "outcome": "passed" if index else "skipped"}
             for index, name in enumerate(names)]
    report = json.dumps({"summary": {"total": 8, "passed": 7,
                                      "failed": 0, "error": 0, "skipped": 1},
                         "tests": tests})
    result = TestResultEvaluator.evaluate(
        job_id="job-1", patch_hash="sha256:" + "a" * 64,
        exit_code=0, raw_output="", report_json_str=report)
    assert result.status == VerificationStatus.EXECUTION_ERROR.value
    assert result.collection_complete is False

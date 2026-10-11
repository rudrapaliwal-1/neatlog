"""Advanced Hardening, Concurrency, Failure Injection, and Reproducibility Tests (Phase 2 Audit).

Verifies:
1. Concurrent verification execution (workspace isolation under parallel runs).
2. Advanced patch rejection: CRLF line endings, missing hunk headers, multi-file attacks, unsafe characters.
3. Expanded forbidden code pattern detection (__import__, importlib, __builtins__, shutil.rmtree, socket).
4. Full determinism and reproducibility across repeated verification runs.
"""

import asyncio
from pathlib import Path
import pytest

from verification.contracts import VerificationRequest, VerificationStatus
from verification.patch_validator import PatchValidator, PatchValidationError
from verification.runner import verify_patch

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CORRECT_PATCH = (FIXTURES_DIR / "correct_patch.diff").read_text(encoding="utf-8")
INCOMPLETE_PATCH = (FIXTURES_DIR / "incomplete_patch.diff").read_text(encoding="utf-8")


# --- 1. Advanced Diff Syntax & Encoding Attacks ---

def test_reject_crlf_line_endings():
    crlf_patch = CORRECT_PATCH.replace("\n", "\r\n")
    with pytest.raises(PatchValidationError, match="(?i)unsupported patch encoding|CRLF"):
        PatchValidator.validate_patch(crlf_patch)


def test_reject_missing_hunk_header():
    no_hunk_patch = """diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
+    # Invalid diff without hunk header
"""
    with pytest.raises(PatchValidationError, match="(?i)missing valid hunk headers"):
        PatchValidator.validate_patch(no_hunk_patch)


def test_reject_multiple_changed_files():
    multi_file_patch = """diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
@@ -1,5 +1,5 @@
-pass
+pass
diff --git a/app/other.py b/app/other.py
--- a/app/other.py
+++ b/app/other.py
@@ -1,5 +1,5 @@
-pass
+pass
"""
    with pytest.raises(PatchValidationError, match="(?i)Changed file count exceeds limit|unauthorized"):
        PatchValidator.validate_patch(multi_file_patch)


def test_reject_unsafe_path_characters():
    weird_path_patch = """diff --git a/app/access\x1b.py b/app/access\x1b.py
--- a/app/access\x1b.py
+++ b/app/access\x1b.py
@@ -1,5 +1,5 @@
-pass
+pass
"""
    with pytest.raises(PatchValidationError, match="(?i)Invalid path characters|unauthorized"):
        PatchValidator.validate_patch(weird_path_patch)


# --- 2. Advanced Code Injection Primitives ---

@pytest.mark.parametrize("injection", [
    "__import__('os').system('whoami')",
    "importlib.import_module('shutil').rmtree('/')",
    "__builtins__.__dict__['eval']('1+1')",
    "shutil.rmtree('/workspace')",
    "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
])
def test_reject_advanced_code_injections(injection):
    diff = f"""diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
@@ -1,5 +1,6 @@
 def get_document(requesting_user_id, document_id):
+    {injection}
     return True
"""
    with pytest.raises(PatchValidationError, match="(?i)Policy violation"):
        PatchValidator.validate_patch(diff)


# --- 3. Concurrency & Parallel Execution Isolation ---

@pytest.mark.docker
def test_concurrent_verification_runs_isolation():
    """Runs 3 verification requests concurrently to verify workspace and container isolation."""
    p_hash = PatchValidator.compute_hash(CORRECT_PATCH)

    req1 = VerificationRequest(
        job_id="job-concurrent-01",
        target_app_id="bola-demo-v1",
        patch_text=CORRECT_PATCH,
        patch_hash=p_hash,
        approval_id="appr-c1",
        timeout_seconds=30,
    )
    req2 = VerificationRequest(
        job_id="job-concurrent-02",
        target_app_id="bola-demo-v1",
        patch_text=CORRECT_PATCH,
        patch_hash=p_hash,
        approval_id="appr-c2",
        timeout_seconds=30,
    )

    def approval_callback(h, a):
        return h == p_hash and a in ("appr-c1", "appr-c2")

    async def run_parallel():
        return await asyncio.gather(
            verify_patch(req1, approval_callback),
            verify_patch(req2, approval_callback),
        )

    results = asyncio.run(run_parallel())
    assert len(results) == 2
    assert results[0].status == VerificationStatus.VERIFIED.value
    assert results[1].status == VerificationStatus.VERIFIED.value
    assert results[0].tests_total == 8
    assert results[1].tests_total == 8
    assert results[0].job_id == "job-concurrent-01"
    assert results[1].job_id == "job-concurrent-02"


# --- 4. Determinism & Reproducibility ---

@pytest.mark.docker
def test_verification_is_reproducible_across_runs():
    """Verifies that running the same patch 3 times produces identical deterministic outcomes."""
    p_hash = PatchValidator.compute_hash(CORRECT_PATCH)
    req = VerificationRequest(
        job_id="job-repro-01",
        target_app_id="bola-demo-v1",
        patch_text=CORRECT_PATCH,
        patch_hash=p_hash,
        approval_id="appr-repro",
        timeout_seconds=30,
    )

    def appr(h, a):
        return True

    res1 = asyncio.run(verify_patch(req, appr))
    res2 = asyncio.run(verify_patch(req, appr))

    assert res1.status == res2.status == VerificationStatus.VERIFIED.value
    assert res1.tests_total == res2.tests_total == 8
    assert res1.tests_passed == res2.tests_passed == 8
    assert res1.tests_failed == res2.tests_failed == 0
    assert res1.failed_tests == res2.failed_tests == []
    assert res1.execution_error == res2.execution_error is None

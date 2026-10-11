from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.schemas import AgentProposal, VerificationResult


TOKEN = "local-test-secret-0123456789abcdef0123456789"

PATCH = """diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
@@ -1 +1 @@
-return document
+return document if owner else None
"""


class FakeAgent:
    def __init__(self):
        self.calls = []

    def propose_patch(self, finding, source_context, attempt, feedback=None):
        self.calls.append((finding, source_context, attempt, feedback))
        return AgentProposal(root_cause="missing owner check", explanation="check owner",
                             patch_format="unified_diff", patch_text=PATCH.replace("+return document if owner else None",
                                                     f"+return document if owner else None  # revision {attempt}"),
                             files_changed=["app/access.py"])


class FakeVerifier:
    def __init__(self, statuses=None):
        self.statuses = list(statuses or ["PASSED"])
        self.calls = []

    def verify_patch(self, request, approval_verifier):
        assert approval_verifier(request.job_id, request.patch_id,
                                 request.patch_hash, request.approval_id)
        self.calls.append(request)
        status = self.statuses.pop(0)
        return VerificationResult(status=status, tests_total=2,
                                  tests_passed=2 if status == "PASSED" else 1,
                                  tests_failed=0 if status == "PASSED" else 1,
                                  failed_tests=[] if status == "PASSED" else ["test_non_owner_access"],
                                  duration_ms=15, test_suite_id=request.verification_profile,
                                  tests_collected=2, collection_complete=True,
                                  execution_completed=True, run_id=request.run_id,
                                  patch_hash=request.patch_hash, source_revision=request.source_revision,
                                  verification_profile=request.verification_profile)


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "source" / "app"
    source.mkdir(parents=True)
    (source / "access.py").write_text("return document\n", encoding="utf-8", newline="\n")
    settings = Settings(database_path=tmp_path / "sentinel.db",
                        source_root=tmp_path / "source", operator_token=TOKEN)
    agent = FakeAgent()
    verifier = FakeVerifier()
    client = TestClient(create_app(settings, agent, verifier),
                        headers={"X-Operator-Token": TOKEN})
    return client, agent, verifier, settings


@pytest.fixture
def finding():
    return {"target_app_id": "bola-demo-v1", "finding": {
        "id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
        "severity": "HIGH", "file_path": "app/access.py",
        "description": "A user can access another user's document."}}


@pytest.fixture
def operator_headers():
    return {"X-Operator-Token": TOKEN}

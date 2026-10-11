"""Real Phase 4 backend-to-Docker-verifier integration evidence."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.schemas import AgentProposal
from backend.services.verification_adapter import ConfiguredVerificationAdapter
from .conftest import TOKEN


ROOT = Path(__file__).resolve().parents[2]
VERIFIER_ROOT = ROOT / "verification"
FINDING = {"target_app_id": "bola-demo-v1", "finding": {
    "id": "BOLA-REAL-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
    "severity": "HIGH", "file_path": "app/access.py",
    "description": "Object owner is not checked."}}


class FixtureAgent:
    def __init__(self, fixture_name: str):
        self.patch = (VERIFIER_ROOT / "fixtures" / fixture_name).read_text(encoding="utf-8")

    def propose_patch(self, finding, source_context, attempt, feedback=None):
        assert "app/access.py" in source_context
        return AgentProposal(root_cause="missing object ownership check",
                             explanation="apply fixture patch",
                             patch_format="unified_diff",
                             patch_text=self.patch,
                             files_changed=["app/access.py"])


def integrated_client(tmp_path, fixture_name):
    settings = Settings(
        database_path=tmp_path / "phase4.db",
        source_root=VERIFIER_ROOT / "lab",
        protected_tests_root=VERIFIER_ROOT / "protected_tests",
        operator_token=TOKEN,
        verifier_callable="verification.adapter:verify_backend_patch",
        verifier_timeout_seconds=120,
    )
    app = create_app(settings, FixtureAgent(fixture_name),
                     ConfiguredVerificationAdapter(settings))
    return TestClient(app, headers={"X-Operator-Token": TOKEN})


def create_approve(client):
    created = client.post("/api/findings", json=FINDING)
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    assert patch["policy_status"] == "PASSED"
    approved = client.post(f"/api/jobs/{job_id}/approval",
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert approved.status_code == 200
    assert approved.json()["source_revision"].startswith("sha256:")
    return job_id, patch


@pytest.mark.docker
def test_correct_patch_reaches_verified_with_real_docker_evidence(tmp_path):
    client = integrated_client(tmp_path, "correct_patch.diff")
    job_id, patch = create_approve(client)
    response = client.post(f"/api/jobs/{job_id}/verify")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "VERIFIED"
    assert (result["tests_total"], result["tests_passed"], result["tests_failed"]) == (8, 8, 0)
    assert result["tests_collected"] == 8
    assert result["collection_complete"] is True
    assert result["execution_completed"] is True
    assert result["test_suite_id"] == "bola-required-tests-v1"
    assert result["patch_hash"] == patch["patch_hash"]
    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert evidence["conclusion"] == "VERIFIED"
    assert evidence["source_revision_current"] is True
    assert evidence["verification_runs"][0]["attestation_integrity"] == "VALID"


@pytest.mark.docker
def test_incomplete_patch_reports_verification_failed_with_real_docker(tmp_path):
    client = integrated_client(tmp_path, "incomplete_patch.diff")
    job_id, patch = create_approve(client)
    response = client.post(f"/api/jobs/{job_id}/verify")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "VERIFICATION_FAILED"
    assert result["tests_total"] == 8
    assert result["tests_failed"] > 0
    assert result["patch_hash"] == patch["patch_hash"]
    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert evidence["conclusion"] == "NOT_VERIFIED"
    assert evidence["verification_runs"][0]["status"] == "VERIFICATION_FAILED"
    assert evidence["verification_runs"][0]["attestation_integrity"] == "VALID"


def test_protected_suite_drift_invalidates_approval_before_docker(tmp_path):
    import shutil
    target = tmp_path / "lab"
    tests = tmp_path / "protected_tests"
    shutil.copytree(VERIFIER_ROOT / "lab", target)
    shutil.copytree(VERIFIER_ROOT / "protected_tests", tests)
    settings = Settings(
        database_path=tmp_path / "drift.db", source_root=target,
        protected_tests_root=tests, operator_token=TOKEN,
        verifier_callable="verification.adapter:verify_backend_patch",
    )
    client = TestClient(create_app(settings, FixtureAgent("correct_patch.diff"),
                                   ConfiguredVerificationAdapter(settings)),
                        headers={"X-Operator-Token": TOKEN})
    job_id, _ = create_approve(client)
    with (tests / "test_security.py").open("a", encoding="utf-8") as test_file:
        test_file.write("\n# changed after approval\n")
    response = client.post(f"/api/jobs/{job_id}/verify")
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_SOURCE_REVISION"
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "EXECUTION_ERROR"

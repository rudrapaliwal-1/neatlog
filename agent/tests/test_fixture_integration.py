"""Fixture-driven wiring test; fixture diffs are not AI inference results."""
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.policy import patch_hash

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "phase5-fixture-operator-token-0123456789"
FINDING = {"target_app_id": "bola-demo-v1", "finding": {
    "id": "BOLA-PHASE5-FIXTURE", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
    "severity": "HIGH", "file_path": "app/access.py",
    "description": "The document access function omits an owner check."}}


def fixture_proposal(name):
    return {"root_cause": "missing owner check", "explanation": "fixture wiring test",
            "patch_format": "unified_diff",
            "patch_text": (ROOT / "verification" / "fixtures" / name).read_text(),
            "files_changed": ["app/access.py"]}


@pytest.mark.docker
def test_fixture_failure_revision_requires_fresh_approval_and_real_docker(tmp_path):
    settings = Settings(database_path=tmp_path / "phase5-fixture.db",
                        source_root=ROOT / "verification" / "lab",
                        protected_tests_root=ROOT / "verification" / "protected_tests",
                        operator_token=TOKEN,
                        agent_callable="agent.planner:propose_patch",
                        verifier_callable="verification.adapter:verify_backend_patch",
                        verifier_timeout_seconds=120)
    client = TestClient(create_app(settings), headers={"X-Operator-Token": TOKEN})
    assert client.get("/ready").json()["status"] == "ready"
    calls = []

    def fixture_generation(finding, source_context, attempt, revision_guidance=None):
        assert set(source_context) == {"app/access.py"}
        calls.append((attempt, revision_guidance))
        return fixture_proposal("incomplete_patch.diff" if attempt == 0 else "correct_patch.diff")

    with patch("agent.planner.generate_patch", side_effect=fixture_generation):
        created = client.post("/api/findings", json=FINDING)
        assert created.status_code == 202
        job_id = created.json()["job_id"]
        initial = client.get(f"/api/jobs/{job_id}/patch").json()
        assert initial["attempt"] == 0
        assert initial["patch_hash"] == patch_hash(fixture_proposal("incomplete_patch.diff")["patch_text"])
        assert client.post(f"/api/jobs/{job_id}/approval", json={
            "patch_hash": initial["patch_hash"], "decision": "APPROVE"}).status_code == 200
        failed = client.post(f"/api/jobs/{job_id}/verify")
        assert failed.status_code == 200
        assert failed.json()["status"] == "VERIFICATION_FAILED"
        assert failed.json()["tests_failed"] > 0
        revised = client.get(f"/api/jobs/{job_id}/patch").json()
        assert revised["attempt"] == 1
        assert revised["patch_hash"] != initial["patch_hash"]
        assert calls[0] == (0, None)
        assert calls[1][0] == 1 and "tests failed" in calls[1][1]
        # The old approval cannot authorize the revised hash.
        no_fresh_approval = client.post(f"/api/jobs/{job_id}/verify")
        assert no_fresh_approval.status_code == 409
        assert client.post(f"/api/jobs/{job_id}/approval", json={
            "patch_hash": revised["patch_hash"], "decision": "APPROVE"}).status_code == 200
        verified = client.post(f"/api/jobs/{job_id}/verify")
        assert verified.status_code == 200
        assert verified.json()["status"] == "VERIFIED"
        assert verified.json()["tests_passed"] == 8
        evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
        assert evidence["conclusion"] == "VERIFIED"
        assert len(evidence["verification_runs"]) == 2
        events = client.get(f"/api/jobs/{job_id}/events").json()
        reflections = [event for event in events if event["event_type"].startswith("REFLECTION_")]
        assert [event["event_type"] for event in reflections] == ["REFLECTION_STARTED", "REFLECTION_COMPLETED"]
        assert reflections[0]["event"]["feedback"]["tests_failed"] == 3
        assert reflections[0]["event"]["attempt"] == 1
        assert "patch_text" not in str(reflections)

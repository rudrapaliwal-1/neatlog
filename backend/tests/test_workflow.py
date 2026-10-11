from backend.schemas import AgentProposal, VerificationResult
from .conftest import FakeVerifier, PATCH, TOKEN


def test_retry_reapproval_and_limit(setup, finding, operator_headers):
    client, agent, verifier, _ = setup
    verifier.statuses = ["FAILED", "FAILED", "FAILED"]
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    hashes = []
    for attempt in range(3):
        patch = client.get(f"/api/jobs/{job_id}/patch").json()
        assert patch["attempt"] == attempt
        hashes.append(patch["patch_hash"])
        if attempt:
            assert client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                               json={"patch_hash": hashes[0], "decision": "APPROVE"}).status_code == 409
            assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).status_code == 409
        assert client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"}).status_code == 200
        assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).json()["status"] == "VERIFICATION_FAILED"
    assert len(set(hashes)) == 3
    assert len(agent.calls) == 3
    assert agent.calls[1][3]["failed_tests"] == ["test_non_owner_access"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "RETRY_EXHAUSTED"
    assert len(client.get(f"/api/jobs/{job_id}/evidence").json()["failure_history"]) == 3


def test_policy_rejection(setup, finding):
    client, agent, _, _ = setup
    def invalid(*args, **kwargs):
        return AgentProposal(root_cause="x", explanation="x", patch_format="unified_diff",
                             patch_text=PATCH.replace("app/access.py", "tests/test.py"),
                             files_changed=["tests/test.py"])
    agent.propose_patch = invalid
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "POLICY_REJECTED"
    assert client.get(f"/api/jobs/{job_id}/patch").json()["policy_status"] == "REJECTED"


def test_verifier_error_does_not_claim_success(setup, finding, operator_headers):
    client, _, verifier, _ = setup
    def broken(*args):
        raise RuntimeError("secret verifier detail")
    verifier.verify_patch = broken
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    result = client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).json()
    assert result["status"] == "EXECUTION_ERROR"
    assert "tests_total" not in result
    assert "secret" not in str(result)
    assert client.get(f"/api/jobs/{job_id}/evidence").json()["conclusion"] == "NOT_VERIFIED"


def test_missing_planner_sets_execution_error(setup, finding):
    client, agent, _, _ = setup
    def broken(*args):
        raise RuntimeError("secret planner detail")
    agent.propose_patch = broken
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "EXECUTION_ERROR"
    assert "secret" not in str(client.get(f"/api/jobs/{job_id}/events").json())


def test_verifier_timeout_records_execution_error(setup, finding, operator_headers):
    from dataclasses import replace
    from threading import Event
    from fastapi.testclient import TestClient
    from backend.main import create_app

    _, agent, _, settings = setup
    gate = Event()

    class HangingVerifier:
        def verify_patch(self, request, approval_verifier):
            gate.wait(1)
            return VerificationResult(status="PASSED", tests_total=1, tests_passed=1,
                                      tests_failed=0, duration_ms=1)

    client = TestClient(create_app(replace(settings, verifier_timeout_seconds=0.01),
                                   agent, HangingVerifier()), headers={"X-Operator-Token": TOKEN})
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    result = client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).json()
    gate.set()
    assert result["status"] == "EXECUTION_ERROR"
    assert result["execution_error"] == "verification timed out"
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "EXECUTION_ERROR"

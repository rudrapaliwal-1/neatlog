"""Phase 2 security and concurrency regression tests."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import Settings
from backend.main import create_app
from backend.models import WorkflowError
from backend.policy import patch_hash, validate_patch
from backend.schemas import ApprovalRequest, VerificationResult
from backend.services.agent_adapter import load_callable
from .conftest import PATCH, TOKEN, FakeVerifier


def _new_job(client, finding):
    response = client.post("/api/findings", json=finding)
    assert response.status_code == 202
    return response.json()["job_id"]


def test_api_requires_token_for_findings_and_all_job_reads(setup, finding):
    client, _, _, settings = setup
    anonymous = TestClient(client.app)
    assert anonymous.post("/api/findings", json=finding).status_code == 401
    job_id = _new_job(client, finding)
    for path in ("/api/jobs", f"/api/jobs/{job_id}",
                 f"/api/jobs/{job_id}/patch", f"/api/jobs/{job_id}/events",
                 f"/api/jobs/{job_id}/evidence"):
        response = anonymous.get(path)
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_REQUIRED"
        assert response.headers["cache-control"] == "no-store"
    assert anonymous.get("/health").status_code == 200
    assert anonymous.get("/docs").status_code == 200
    closed = TestClient(create_app(replace(settings, database_path=settings.database_path.with_name("closed.db"),
                                           operator_token="")))
    assert closed.get("/api/jobs", headers={"X-Operator-Token": TOKEN}).status_code == 503


def test_invalid_and_oversized_finding_payloads(setup, finding):
    client, _, _, settings = setup
    variants = [
        {**finding, "extra": "not allowed"},
        {**finding, "finding": {**finding["finding"], "severity": "UNSPECIFIED"}},
        {**finding, "finding": {**finding["finding"], "description": ""}},
        {**finding, "finding": {**finding["finding"], "id": 1}},
    ]
    for payload in variants:
        response = client.post("/api/findings", json=payload)
        assert response.status_code == 422
        assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
        assert "not allowed" not in response.text
    huge = {**finding, "finding": {**finding["finding"],
                                     "description": "secret-must-not-echo" + "A" * settings.max_request_bytes}}
    response = client.post("/api/findings", json=huge)
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"
    assert "secret-must-not-echo" not in response.text
    assert client.get("/api/jobs").json() == []


def test_cors_exact_origin_and_configuration_validation(setup):
    client, _, _, settings = setup
    allowed = client.options("/api/findings", headers={"Origin": settings.frontend_origin,
                                                      "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "X-Operator-Token"})
    assert allowed.headers["access-control-allow-origin"] == settings.frontend_origin
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options("/api/jobs", headers={
            "Origin": origin, "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Operator-Token",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
    wrong_port = client.options("/api/jobs", headers={
        "Origin": "http://127.0.0.1:5174", "Access-Control-Request-Method": "GET",
    })
    assert wrong_port.status_code == 400
    denied = client.options("/api/findings", headers={"Origin": "https://attacker.example",
                                                     "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in denied.headers
    with pytest.raises(ValueError):
        replace(settings, frontend_origin="*")
    with pytest.raises(ValueError):
        replace(settings, frontend_origin="http://attacker.example")
    with pytest.raises(ValueError):
        replace(settings, operator_token="short")
    assert TOKEN not in repr(settings)
    with pytest.raises(ValueError):
        replace(settings, verifier_callable="os:system")


def test_reject_unsafe_dynamic_callable_spec():
    for value in ("os:system", "agent.planner:__getattribute__", "verification.runner:verify_patch"):
        with pytest.raises(RuntimeError):
            load_callable(value, "agent")


def test_invalid_hunks_metadata_and_protected_paths(setup):
    _, _, _, settings = setup
    bad = [
        PATCH.replace("@@ -1 +1 @@", "@@ -1,2 +1 @@"),
        PATCH.replace("@@ -1 +1 @@", "@@ -1 +1,2 @@"),
        PATCH.replace("--- a/app/access.py", "new file mode 100644\n--- a/app/access.py"),
        PATCH.replace("diff --git a/app/access.py b/app/access.py", "diff --git a/../app/access.py b/../app/access.py"),
        PATCH.replace("app/access.py", "tests/test_access.py"),
        PATCH + "unexpected trailing metadata\n",
        PATCH.replace("+return document if owner else None", "+return document if owner else None\n+extra"),
        PATCH.replace("owner else None", "owner\u2028else None"),
    ]
    for text in bad:
        assert not validate_patch("bola-demo-v1", text, ["app/access.py"], 0, settings).allowed


def test_wrong_hash_replay_and_attempt_binding(setup, finding):
    client, _, verifier, _ = setup
    verifier.statuses = ["FAILED", "PASSED"]
    job_id = _new_job(client, finding)
    first = client.get(f"/api/jobs/{job_id}/patch").json()
    base = f"/api/jobs/{job_id}"
    assert client.post(base + "/approval", json={"patch_hash": patch_hash("wrong"),
                                                  "decision": "APPROVE"}).status_code == 409
    assert client.post(base + "/approval", json={"patch_hash": first["patch_hash"],
                                                  "decision": "APPROVE"}).status_code == 200
    assert client.post(base + "/approval", json={"patch_hash": first["patch_hash"],
                                                  "decision": "APPROVE"}).status_code == 409
    assert client.post(base + "/verify").json()["status"] == "VERIFICATION_FAILED"
    revised = client.get(base + "/patch").json()
    assert revised["attempt"] == 1
    assert client.post(base + "/approval", json={"patch_hash": first["patch_hash"],
                                                  "decision": "APPROVE"}).status_code == 409
    with client.app.state.workflow.db.read() as db:
        old_approval = db.execute("SELECT * FROM approvals WHERE patch_id = ?", (first["id"],)).fetchone()
        from backend.approvals import approval_is_active
        assert not approval_is_active(db, job_id, first["id"], first["patch_hash"], old_approval["id"])


def test_concurrent_approval_is_atomic(setup, finding):
    client, _, _, _ = setup
    job_id = _new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    workflow = client.app.state.workflow
    barrier = Barrier(3)
    request = ApprovalRequest(patch_hash=patch["patch_hash"], decision="APPROVE")

    def approve():
        barrier.wait()
        try:
            return workflow.decide(job_id, request, TOKEN)["approval_id"]
        except WorkflowError as error:
            return error.http_status

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(approve)
        second = pool.submit(approve)
        barrier.wait()
        results = [first.result(), second.result()]
    assert results.count(409) == 1
    assert len([value for value in results if isinstance(value, str)]) == 1
    with workflow.db.read() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals WHERE job_id = ?", (job_id,)).fetchone()[0] == 1


def test_duplicate_verification_during_active_run(setup, finding):
    client, agent, _, settings = setup
    entered = Event()
    release = Event()

    class SlowVerifier:
        def verify_patch(self, request, approval_verifier):
            entered.set()
            assert release.wait(3)
            return VerificationResult(status="PASSED", tests_total=1, tests_passed=1,
                                      tests_failed=0, duration_ms=1,
                                      test_suite_id=request.verification_profile, tests_collected=1,
                                      collection_complete=True, execution_completed=True,
                                      run_id=request.run_id, patch_hash=request.patch_hash,
                                      source_revision=request.source_revision,
                                      verification_profile=request.verification_profile)

    app = create_app(replace(settings, database_path=settings.database_path.with_name("concurrent.db")),
                     agent, SlowVerifier())
    slow_client = TestClient(app, headers={"X-Operator-Token": TOKEN})
    job_id = _new_job(slow_client, finding)
    patch = slow_client.get(f"/api/jobs/{job_id}/patch").json()
    assert slow_client.post(f"/api/jobs/{job_id}/approval",
                            json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"}).status_code == 200
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(app.state.workflow.verify, job_id)
        assert entered.wait(3)
        with pytest.raises(WorkflowError):
            app.state.workflow.verify(job_id)
        release.set()
        assert first.result()["status"] == "VERIFIED"
    with app.state.workflow.db.read() as db:
        assert db.execute("SELECT COUNT(*) FROM verification_runs WHERE job_id = ?", (job_id,)).fetchone()[0] == 1


def test_approval_transaction_rolls_back_on_event_failure(setup, finding, monkeypatch):
    client, _, _, _ = setup
    job_id = _new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    workflow = client.app.state.workflow

    def fail_event(*args, **kwargs):
        raise RuntimeError("event storage failed")

    monkeypatch.setattr(workflow, "_event", fail_event)
    with pytest.raises(RuntimeError):
        workflow.decide(job_id, ApprovalRequest(patch_hash=patch["patch_hash"], decision="APPROVE"), TOKEN)
    with workflow.db.read() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals WHERE job_id = ?", (job_id,)).fetchone()[0] == 0
        assert db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()[0] == "AWAITING_APPROVAL"


def test_interrupted_verification_is_not_verified_after_restart(setup, finding):
    client, agent, verifier, settings = setup
    job_id = _new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    client.post(f"/api/jobs/{job_id}/approval",
                json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    workflow = client.app.state.workflow
    with workflow.db.transaction() as db:
        db.execute("""INSERT INTO verification_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                   ("run-interrupted", job_id, patch["id"], patch["patch_hash"],
                    "RUNNING", "{}", "2026-01-01T00:00:00+00:00", None))
    restored = create_app(settings, agent, verifier).state.workflow
    assert restored.get_job(job_id)["status"] == "EXECUTION_ERROR"
    evidence = restored.evidence(job_id)
    assert evidence["conclusion"] == "NOT_VERIFIED"
    assert evidence["verification_runs"][0]["status"] == "EXECUTION_ERROR"
    assert evidence["verification_runs"][0]["result"]["execution_error"] == "process interrupted"


def test_malformed_agent_and_sensitive_verifier_result_are_redacted(setup, finding):
    client, agent, verifier, _ = setup
    def malformed(*args):
        return {"patch_format": "shell", "patch_text": "rm -rf /", "root_cause": "x",
                "explanation": "x", "files_changed": ["app/access.py"]}
    agent.propose_patch = malformed
    job_id = _new_job(client, finding)
    events = client.get(f"/api/jobs/{job_id}/events").json()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "EXECUTION_ERROR"
    assert "malformed planner proposal" in str(events)
    assert "rm -rf" not in str(events)

    from .conftest import FakeAgent
    client.app.state.workflow.agent = FakeAgent()
    next_job = _new_job(client, finding)
    patch = client.get(f"/api/jobs/{next_job}/patch").json()
    client.post(f"/api/jobs/{next_job}/approval",
                json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    def sensitive(*args):
        return VerificationResult(status="EXECUTION_ERROR", tests_total=0, tests_passed=0,
                                  tests_failed=0, duration_ms=1,
                                  execution_error="private-token-should-not-appear")
    verifier.verify_patch = sensitive
    result = client.post(f"/api/jobs/{next_job}/verify").json()
    assert result["status"] == "EXECUTION_ERROR"
    assert "private-token-should-not-appear" not in str(result)
    assert "private-token-should-not-appear" not in str(client.get(f"/api/jobs/{next_job}/evidence").json())


def test_evidence_detects_patch_tampering_and_events_are_append_only(setup, finding):
    import sqlite3

    client, _, _, _ = setup
    job_id = _new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    workflow = client.app.state.workflow
    with pytest.raises(sqlite3.IntegrityError):
        with workflow.db.transaction() as db:
            db.execute("DELETE FROM workflow_events WHERE job_id = ?", (job_id,))
    with workflow.db.transaction() as db:
        db.execute("UPDATE patch_proposals SET patch_text = ? WHERE id = ?",
                   ("tampered", patch["id"]))
    evidence = workflow.evidence(job_id)
    assert evidence["patch_attempts"][0]["hash_integrity"] == "MISMATCH"
    assert evidence["integrity_issues"]
    assert evidence["conclusion"] == "NOT_VERIFIED"


def test_job_listing_is_bounded_and_paginated(setup, finding):
    client, _, _, _ = setup
    _new_job(client, finding)
    _new_job(client, finding)
    assert len(client.get("/api/jobs?limit=1").json()) == 1
    assert len(client.get("/api/jobs?limit=1&offset=1").json()) == 1
    assert client.get("/api/jobs?limit=101").status_code == 422
    assert client.get("/api/jobs?offset=-1").status_code == 422


def test_existing_database_approval_attempt_migrates(setup, finding):
    from backend.database import Database

    client, _, _, settings = setup
    job_id = _new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    db = client.app.state.workflow.db
    with db.transaction() as connection:
        connection.execute("ALTER TABLE approvals DROP COLUMN attempt")
        connection.execute("""INSERT INTO approvals
                            (id, job_id, patch_id, patch_hash, decision, approved_by, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                           ("legacy-approval", job_id, patch["id"], patch["patch_hash"],
                            "APPROVE", "local-operator", "2026-01-01T00:00:00+00:00"))
    migrated = Database(settings.database_path)
    with migrated.read() as connection:
        row = connection.execute("SELECT attempt FROM approvals WHERE id = 'legacy-approval'").fetchone()
    assert row["attempt"] == 0

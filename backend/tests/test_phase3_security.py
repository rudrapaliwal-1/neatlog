"""Negative tests for Phase 3 trust and persistence invariants."""

from dataclasses import replace
import sqlite3
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.manifest import TARGET_MANIFEST
from backend.models import Status, WorkflowError
from backend.schemas import VerificationResult
from .conftest import TOKEN


def new_job(client, finding):
    response = client.post("/api/findings", json=finding)
    assert response.status_code == 202
    return response.json()["job_id"]


def approve(client, job_id):
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    response = client.post(f"/api/jobs/{job_id}/approval",
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert response.status_code == 200
    return patch, response.json()


def test_manifest_revision_binding(setup, finding):
    client, _, _, settings = setup
    job_id = new_job(client, finding)
    first = client.get(f"/api/jobs/{job_id}/evidence").json()["target_binding"]
    assert first["verification_profile"] == TARGET_MANIFEST.verification_profile
    assert first["source_revision"].startswith("sha256:")


def test_manifest_revision_and_symlink_rejected(setup, finding, tmp_path):
    client, _, _, settings = setup
    target = settings.source_root / "app" / "access.py"
    target.unlink()
    try:
        target.symlink_to(tmp_path / "elsewhere")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege unavailable; run this test in the Linux test container")
        raise
    response = client.post("/api/findings", json=finding)
    assert response.status_code == 503
    assert response.json()["code"] == "SOURCE_UNAVAILABLE"


def test_source_change_invalidates_proposal_and_approval(setup, finding):
    client, _, _, settings = setup
    job_id = new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    (settings.source_root / "app" / "access.py").write_text("new revision\n")
    response = client.post(f"/api/jobs/{job_id}/approval",
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_SOURCE_REVISION"
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "EXECUTION_ERROR"
    assert client.get(f"/api/jobs/{job_id}/evidence").json()["conclusion"] == "NOT_VERIFIED"


def test_source_change_after_approval_prevents_launch(setup, finding):
    client, _, verifier, settings = setup
    job_id = new_job(client, finding)
    approve(client, job_id)
    (settings.source_root / "app" / "access.py").write_text("changed\n")
    response = client.post(f"/api/jobs/{job_id}/verify")
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_SOURCE_REVISION"
    assert verifier.calls == []


@pytest.mark.parametrize("field,value", [
    ("test_suite_id", "wrong-suite"),
    ("tests_collected", 0),
    ("collection_complete", False),
    ("execution_completed", False),
    ("run_id", "run-" + "0" * 32),
    ("patch_hash", "sha256:" + "0" * 64),
    ("source_revision", "sha256:" + "0" * 64),
    ("verification_profile", "wrong-profile"),
])
def test_forged_or_incomplete_success_fails_closed(setup, finding, field, value):
    client, _, verifier, _ = setup
    def forged(request, approval_verifier):
        data = dict(status="PASSED", tests_total=2, tests_passed=2, tests_failed=0,
                    duration_ms=1, test_suite_id=request.verification_profile,
                    tests_collected=2, collection_complete=True, execution_completed=True,
                    run_id=request.run_id, patch_hash=request.patch_hash,
                    source_revision=request.source_revision,
                    verification_profile=request.verification_profile)
        data[field] = value
        return VerificationResult(**data)
    verifier.verify_patch = forged
    job_id = new_job(client, finding)
    approve(client, job_id)
    response = client.post(f"/api/jobs/{job_id}/verify")
    assert response.json()["status"] == "EXECUTION_ERROR"
    assert client.get(f"/api/jobs/{job_id}/evidence").json()["conclusion"] == "NOT_VERIFIED"


def test_missing_report_and_zero_tests_fail_closed(setup, finding):
    client, _, verifier, _ = setup
    verifier.verify_patch = lambda request, approval_verifier: {
        "status": "PASSED", "tests_total": 0, "tests_passed": 0,
        "tests_failed": 0, "duration_ms": 1,
    }
    job_id = new_job(client, finding)
    approve(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/verify").json()["status"] == "EXECUTION_ERROR"


def test_evidence_digest_detects_run_tampering(setup, finding):
    client, _, _, _ = setup
    job_id = new_job(client, finding)
    approve(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/verify").json()["status"] == "VERIFIED"
    workflow = client.app.state.workflow
    with workflow.db.transaction() as db:
        db.execute("UPDATE verification_runs SET result_json = ? WHERE job_id = ?",
                   ('{"status":"PASSED","tests_total":2,"tests_failed":0}', job_id))
    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert evidence["conclusion"] == "NOT_VERIFIED"
    assert any("attestation digest mismatch" in issue for issue in evidence["integrity_issues"])


def test_live_lease_survives_second_instance_startup(setup, finding):
    client, agent, _, settings = setup
    entered = Event()
    release = Event()
    class SlowVerifier:
        def verify_patch(self, request, approval_verifier):
            entered.set()
            assert release.wait(3)
            return VerificationResult(status="PASSED", tests_total=1, tests_passed=1,
                                      tests_failed=0, duration_ms=1,
                                      test_suite_id=request.verification_profile,
                                      tests_collected=1, collection_complete=True,
                                      execution_completed=True, run_id=request.run_id,
                                      patch_hash=request.patch_hash, source_revision=request.source_revision,
                                      verification_profile=request.verification_profile)
    app = create_app(replace(settings, database_path=settings.database_path.with_name("lease.db")),
                     agent, SlowVerifier())
    slow = TestClient(app, headers={"X-Operator-Token": TOKEN})
    job_id = new_job(slow, finding)
    approve(slow, job_id)
    result = []
    thread = Thread(target=lambda: result.append(app.state.workflow.verify(job_id)))
    thread.start()
    assert entered.wait(2)
    restored = create_app(replace(settings, database_path=settings.database_path.with_name("lease.db")),
                          agent, SlowVerifier())
    assert restored.state.workflow.get_job(job_id)["status"] == "VERIFYING"
    release.set()
    thread.join(3)
    assert result[0]["status"] == "VERIFIED"


def test_expired_lease_discards_late_verifier_result(setup, finding):
    client, agent, _, settings = setup
    entered = Event()
    release = Event()
    class SlowVerifier:
        def verify_patch(self, request, approval_verifier):
            entered.set()
            release.wait(3)
            return VerificationResult(status="PASSED", tests_total=1, tests_passed=1,
                                      tests_failed=0, duration_ms=1,
                                      test_suite_id=request.verification_profile,
                                      tests_collected=1, collection_complete=True,
                                      execution_completed=True, run_id=request.run_id,
                                      patch_hash=request.patch_hash, source_revision=request.source_revision,
                                      verification_profile=request.verification_profile)
    app = create_app(replace(settings, database_path=settings.database_path.with_name("late.db")),
                     agent, SlowVerifier())
    slow = TestClient(app, headers={"X-Operator-Token": TOKEN})
    job_id = new_job(slow, finding)
    approve(slow, job_id)
    errors = []
    def verify():
        try:
            app.state.workflow.verify(job_id)
        except WorkflowError as error:
            errors.append(error.code)
    thread = Thread(target=verify)
    thread.start()
    assert entered.wait(2)
    with app.state.workflow.db.transaction() as db:
        db.execute("UPDATE verification_leases SET expires_at = '2020-01-01T00:00:00+00:00'")
    app.state.workflow.recover_interrupted()
    release.set()
    thread.join(3)
    assert errors == ["LEASE_LOST"]
    assert app.state.workflow.get_job(job_id)["status"] == "EXECUTION_ERROR"


def test_cas_and_lock_contention(setup, finding):
    client, _, _, _ = setup
    job_id = new_job(client, finding)
    workflow = client.app.state.workflow
    with workflow.db.transaction() as db:
        job = workflow._job(db, job_id)
        job["version"] -= 1
        with pytest.raises(WorkflowError) as exc:
            workflow._transition(db, job, Status.VERIFYING)
        assert exc.value.code == "STATE_CONFLICT"
    holder = workflow.db.connect()
    contender = workflow.db.connect()
    try:
        contender.execute("PRAGMA busy_timeout = 1")
        holder.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError):
            contender.execute("BEGIN IMMEDIATE")
    finally:
        holder.rollback()
        holder.close()
        contender.close()


def test_environment_and_forensic_headers(setup, finding):
    client, _, _, settings = setup
    with pytest.raises(ValueError, match="production identity"):
        replace(settings, environment="production")
    response = client.post("/api/findings", json=finding)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    job_id = response.json()["job_id"]
    events = client.get(f"/api/jobs/{job_id}/events").json()
    assert events[0]["event"]["correlation_id"] == response.headers["x-correlation-id"]
    assert events[0]["event"]["job_id"] == job_id


def test_protected_test_change_invalidates_approval(setup, finding):
    client, _, _, settings = setup
    tests_dir = settings.source_root / "tests"
    tests_dir.mkdir()
    suite = tests_dir / "test_access.py"
    suite.write_text("def test_access(): assert True\n")
    job_id = new_job(client, finding)
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    suite.write_text("def test_access(): assert False\n")
    response = client.post(f"/api/jobs/{job_id}/approval",
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert response.json()["code"] == "STALE_SOURCE_REVISION"


def test_evidence_fails_if_approval_binding_is_removed(setup, finding):
    client, _, _, _ = setup
    job_id = new_job(client, finding)
    approve(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/verify").json()["status"] == "VERIFIED"
    with client.app.state.workflow.db.transaction() as db:
        db.execute("DELETE FROM approval_bindings WHERE approval_id IN "
                   "(SELECT id FROM approvals WHERE job_id = ?)", (job_id,))
    assert client.get(f"/api/jobs/{job_id}/evidence").json()["conclusion"] == "NOT_VERIFIED"


def test_diff_unicode_and_duplicate_headers_rejected(setup):
    from backend.policy import validate_patch
    from .conftest import PATCH
    _, _, _, settings = setup
    variants = [
        PATCH.replace("app/access.py", "app/accés.py"),
        PATCH.replace("app/access.py", "app/acce\u0301s.py"),
        PATCH + PATCH,
        PATCH.replace("--- a/app/access.py", "--- a/../app/access.py"),
        PATCH.replace("+++ b/app/access.py", "+++ b//app/access.py"),
    ]
    for candidate in variants:
        assert not validate_patch("bola-demo-v1", candidate, ["app/access.py"], 0, settings).allowed


def test_readiness_requires_demo_token_and_integration_adapters(setup, tmp_path):
    client, _, _, settings = setup
    assert client.get("/ready").status_code == 200
    from backend.main import create_app
    unconfigured = TestClient(create_app(replace(settings, database_path=tmp_path / "empty.db",
                                                  operator_token="")))
    assert unconfigured.get("/health").status_code == 200
    assert unconfigured.get("/ready").status_code == 503


def test_source_change_while_verifier_running_closes_run(setup, finding):
    client, agent, _, settings = setup
    entered = Event()
    release = Event()
    class SlowVerifier:
        def verify_patch(self, request, approval_verifier):
            entered.set()
            release.wait(3)
            return VerificationResult(status="PASSED", tests_total=1, tests_passed=1,
                                      tests_failed=0, duration_ms=1,
                                      test_suite_id=request.verification_profile,
                                      tests_collected=1, collection_complete=True,
                                      execution_completed=True, run_id=request.run_id,
                                      patch_hash=request.patch_hash,
                                      source_revision=request.source_revision,
                                      verification_profile=request.verification_profile)
    app = create_app(replace(settings, database_path=settings.database_path.with_name("revision-race.db")),
                     agent, SlowVerifier())
    local = TestClient(app, headers={"X-Operator-Token": TOKEN})
    job_id = new_job(local, finding)
    patch, _ = approve(local, job_id)
    errors = []
    def verify():
        try:
            app.state.workflow.verify(job_id)
        except WorkflowError as error:
            errors.append(error.code)
    thread = Thread(target=verify)
    thread.start()
    assert entered.wait(2)
    (settings.source_root / "app" / "access.py").write_text("changed during verify\n")
    stale = local.post(f"/api/jobs/{job_id}/approval",
                       json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert stale.json()["code"] == "STALE_SOURCE_REVISION"
    release.set()
    thread.join(3)
    assert errors == ["LEASE_LOST"]
    with app.state.workflow.db.read() as db:
        assert db.execute("SELECT status FROM verification_runs WHERE job_id = ?",
                          (job_id,)).fetchone()[0] == "EXECUTION_ERROR"


def test_planner_context_limit_fails_closed(setup, finding):
    client, agent, _, settings = setup
    (settings.source_root / "app" / "access.py").write_bytes(b"x" * (settings.max_source_bytes + 1))
    job_id = new_job(client, finding)
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "EXECUTION_ERROR"
    assert agent.calls == []

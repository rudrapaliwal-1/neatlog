"""Privacy contract and real workflow hooks for the approved nine events."""
from pathlib import Path

import pytest

from backend.lifecycle_telemetry import EVENT_NAMES, SAFE_FIELDS, LifecycleTelemetry, format_event
from backend.tests.test_product import archive, product, register, ROOT

CORRELATION = "a" * 32
APPROVED = [
    "project.uploaded", "finding.submitted", "agent.inference.started",
    "agent.inference.completed", "patch.generated", "patch.validation.completed",
    "approval.recorded", "verification.started", "verification.completed",
]


def test_exact_event_vocabulary_and_metadata_contract():
    assert EVENT_NAMES == set(APPROVED)
    assert SAFE_FIELDS == {"correlation_id", "run_id", "attempt", "success",
                           "duration_ms", "tests_passed", "tests_failed"}
    for name in APPROVED:
        assert format_event(name, {"correlation_id": CORRELATION, "attempt": 0}) == {
            "event": name, "correlation_id": CORRELATION, "attempt": 0}
    for name in ("agent.reflection.started", "agent.reflection.completed", "source.exported"):
        with pytest.raises(ValueError):
            format_event(name, {"correlation_id": CORRELATION})


@pytest.mark.parametrize("field,value", [
    ("source", "def private(): pass"), ("patch_text", "diff --git secret"),
    ("email", "alice@example.test"), ("session_token", "session-secret"),
    ("api_key", "api-secret"), ("test_log", "raw verifier output"),
    ("exception", "private exception"), ("file_path", "app/access.py"),
    ("description", "user-controlled finding"), ("request_body", "raw upload"),
    ("ip_address", "127.0.0.1"), ("job_id", "job-" + "b" * 32),
])
def test_sensitive_and_unexpected_fields_rejected(field, value):
    with pytest.raises(ValueError):
        format_event("finding.submitted", {"correlation_id": CORRELATION, field: value})


@pytest.mark.parametrize("field,value", [
    ("correlation_id", "../../private"), ("run_id", "run-" + "b" * 32),
    ("attempt", True), ("attempt", 3), ("success", "PASSED"),
    ("tests_failed", -1), ("duration_ms", "15"),
])
def test_invalid_allowed_values_rejected(field, value):
    with pytest.raises(ValueError):
        format_event("verification.completed", {"correlation_id": CORRELATION, field: value})


def test_local_mode_no_network_and_bounded_buffer():
    telemetry = LifecycleTelemetry(mode="local")
    for _ in range(300):
        telemetry.emit("finding.submitted", correlation_id=telemetry.correlation_for("internal-job"),
                       attempt=0, success=True)
    assert len(telemetry.local_events) == 256
    assert len({item["correlation_id"] for item in telemetry.local_events}) == 1
    assert telemetry.sent == 0


def test_full_owned_project_lifecycle_and_privacy(product):
    workflow = product.state.workflow
    workflow.telemetry = LifecycleTelemetry(mode="local")
    client, headers = register(product, "private.alice@example.test")
    project_id = client.post("/api/projects", json={"name": "private project"}, headers=headers).json()["id"]
    lab = ROOT / "verification" / "lab" / "app"
    data = archive({"requirements.txt": "fastapi==0.143.0\n", "app/__init__.py": "",
                    "app/access.py": (lab / "access.py").read_bytes(),
                    "app/sample_data.py": (lab / "sample_data.py").read_bytes()})
    upload = client.post(f"/api/projects/{project_id}/upload",
                         headers={**headers, "Content-Type": "application/zip"}, content=data)
    assert upload.status_code == 200, upload.text
    finding = {"target_app_id": project_id, "finding": {
        "id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
        "severity": "HIGH", "file_path": "app/access.py",
        "description": "private vulnerability details and api-secret"}}
    submitted = client.post("/api/findings", json=finding, headers=headers)
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    assert patch["policy_status"] == "PASSED", patch
    assert client.post(f"/api/jobs/{job_id}/verify", headers=headers).status_code == 409
    approval = client.post(f"/api/jobs/{job_id}/approval", headers=headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert approval.status_code == 200, approval.text
    verified = client.post(f"/api/jobs/{job_id}/verify", headers=headers)
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "VERIFIED"
    events = list(workflow.telemetry.local_events)
    assert [event["event"] for event in events] == APPROVED
    assert len({event["correlation_id"] for event in events}) == 1
    assert events[2]["attempt"] == 0 and events[3]["success"] is True
    assert events[-1]["success"] is True and events[-1]["tests_passed"] == 2
    assert events[-2]["run_id"] == events[-1]["run_id"]
    text = str(events)
    for secret in ("private.alice@example.test", "private project", "api-secret",
                   "app/access.py", "diff --git", project_id, job_id):
        assert secret not in text


def test_final_sdk_export_mask_removes_incidental_sensitive_data():
    from backend.lifecycle_telemetry import export_mask
    span = {"name": "verification.completed", "attributes": {
        "neatlogs.workflow.correlation_id": CORRELATION,
        "neatlogs.workflow.attempt": 0, "neatlogs.workflow.success": True,
        "neatlogs.workflow.tests_passed": 8, "neatlogs.workflow.tests_failed": 0,
        "http.request.body": "session-secret", "user.email": "alice@example.test",
        "source.file": "app/access.py", "exception.message": "private exception",
        "neatlogs.prompt": "raw prompt"},
        "events": [{"name": "raw verifier output"}],
        "links": [{"trace_id": "private"}],
        "resource": {"attributes": {"host.name": "private host", "process.command_line": "api-secret"}},
        "status": {"code": "ERROR", "description": "private exception"}}
    masked = export_mask(span)
    assert masked is not None
    assert set(masked["attributes"]) == {
        "neatlogs.workflow.correlation_id", "neatlogs.workflow.attempt", "neatlogs.workflow.success",
        "neatlogs.workflow.tests_passed", "neatlogs.workflow.tests_failed"}
    assert masked["events"] == masked["links"] == []
    assert masked["resource"] == {"attributes": {}}
    for secret in ("session-secret", "alice@example.test", "app/access.py",
                   "private exception", "raw prompt", "raw verifier output", "api-secret"):
        assert secret not in str(masked)
    assert export_mask({"name": "agent.reflection.started", "attributes": {}}) is None
    assert export_mask({"name": "finding.submitted", "attributes": {"user.email": "alice@example.test"}}) is None


def test_inference_failure_uses_boolean_without_exception_text(setup, finding):
    client, agent, _, _ = setup
    telemetry = LifecycleTelemetry(mode="local")
    client.app.state.workflow.telemetry = telemetry
    def broken(*args, **kwargs):
        raise RuntimeError("private exception with api-secret and app/access.py")
    agent.propose_patch = broken
    submitted = client.post("/api/findings", json=finding)
    assert submitted.status_code == 202
    events = list(telemetry.local_events)
    assert [item["event"] for item in events] == [
        "finding.submitted", "agent.inference.started", "agent.inference.completed"]
    assert events[-1]["success"] is False
    assert "private exception" not in str(events) and "api-secret" not in str(events)


def test_failed_verification_retry_has_one_event_per_attempt(setup, finding, operator_headers):
    client, _, verifier, _ = setup
    telemetry = LifecycleTelemetry(mode="local")
    client.app.state.workflow.telemetry = telemetry
    verifier.statuses = ["FAILED", "PASSED"]
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    first = client.get(f"/api/jobs/{job_id}/patch").json()
    assert client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                       json={"patch_hash": first["patch_hash"], "decision": "APPROVE"}).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).json()["status"] == "VERIFICATION_FAILED"
    second = client.get(f"/api/jobs/{job_id}/patch").json()
    assert second["attempt"] == 1
    assert client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                       json={"patch_hash": second["patch_hash"], "decision": "APPROVE"}).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).json()["status"] == "VERIFIED"
    events = list(telemetry.local_events)
    completions = [item for item in events if item["event"] == "verification.completed"]
    assert len(completions) == 2
    assert [(item["attempt"], item["success"], item["tests_passed"], item["tests_failed"])
            for item in completions] == [(0, False, 1, 1), (1, True, 2, 0)]
    assert len({item["run_id"] for item in completions}) == 2
    assert len({item["correlation_id"] for item in events}) == 1


def test_export_failure_cannot_change_verdict(setup, finding, operator_headers):
    client, _, _, _ = setup
    class BrokenTelemetry:
        mode = "local"
        def emit(self, *args, **kwargs):
            raise RuntimeError("neatlogs unavailable with secret details")
    client.app.state.workflow.telemetry = BrokenTelemetry()
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    assert client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                       json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"}).status_code == 200
    result = client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "VERIFIED"


def test_random_correlation_persists_across_database_reopen(tmp_path):
    from backend.database import Database
    from backend.workflow import Workflow
    path = tmp_path / "telemetry.db"
    first_db = Database(path)
    with first_db.transaction() as db:
        first = Workflow._opaque_telemetry_id(db, "scope:project-internal-secret")
    reopened = Database(path)
    with reopened.transaction() as db:
        second = Workflow._opaque_telemetry_id(db, "scope:project-internal-secret")
        run = Workflow._opaque_telemetry_id(db, "run:database-run-secret")
    assert first == second and len(first) == 32
    assert first != run and "secret" not in first


def test_hosted_initialization_failure_is_bounded_and_does_not_expose_key(monkeypatch):
    from time import monotonic, sleep
    monkeypatch.setenv("NEATLOGS_API_KEY", "private-key")
    class FailedSDK:
        def init(self, **kwargs):
            raise RuntimeError("private-key in SDK failure")
    telemetry = LifecycleTelemetry(mode="hosted", sdk=FailedSDK())
    deadline = monotonic() + 1
    while telemetry.failure_category is None and monotonic() < deadline:
        sleep(0.001)
    assert telemetry.failure_category == "sdk_initialization_failed"
    for _ in range(300):
        telemetry.emit("finding.submitted", correlation_id=CORRELATION, attempt=0, success=True)
    assert telemetry._queue.qsize() == 256
    assert telemetry.dropped == 44
    assert "private-key" not in str(telemetry.failure_category)

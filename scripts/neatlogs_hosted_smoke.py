"""Controlled nine-event hosted Neatlogs smoke with real Docker verification.

Use only after local privacy tests pass. Loads the existing .env key in memory;
never prints it. This uses a known fixture patch to make delivery repeatable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.schemas import AgentProposal
from backend.services.verification_adapter import ConfiguredVerificationAdapter
from backend.lifecycle_telemetry import EVENT_NAMES, MASK_COUNTS

ROOT = Path(__file__).resolve().parents[1]


def load_key() -> bool:
    for line in (ROOT / ".env").read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip().removeprefix("export ").strip() == "NEATLOGS_API_KEY":
            key = value.strip().strip('"\'')
            if key:
                os.environ["NEATLOGS_API_KEY"] = key
                return True
    return False


class FixtureAgent:
    def propose_patch(self, finding, source_context, attempt, feedback=None):
        patch = (ROOT / "verification" / "fixtures" / "correct_patch.diff").read_text()
        return AgentProposal(root_cause="fixture", explanation="fixture",
                             patch_format="unified_diff", patch_text=patch,
                             files_changed=["app/access.py"])


def archive() -> bytes:
    lab = ROOT / "verification" / "lab" / "app"
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("requirements.txt", "fastapi==0.143.0\n")
        output.writestr("app/__init__.py", "")
        for name in ("access.py", "sample_data.py"):
            output.writestr("app/" + name, (lab / name).read_bytes())
    return stream.getvalue()


def main() -> int:
    if not load_key():
        print(json.dumps({"status": "blocked", "category": "missing_api_key"}))
        return 2
    os.environ["SENTINEL_NEATLOGS_MODE"] = "hosted"
    evidence_root = ROOT / "local-audit" / ("neatlogs-" + uuid4().hex)
    evidence_root.mkdir(mode=0o700, parents=True)
    settings = Settings(database_path=evidence_root / "workflow.db",
                        source_root=ROOT / "verification" / "lab",
                        protected_tests_root=ROOT / "verification" / "protected_tests",
                        project_root=evidence_root / "projects", operator_token="",
                        verifier_callable="verification.adapter:verify_backend_patch",
                        verifier_timeout_seconds=120)
    app = create_app(settings, FixtureAgent(), ConfiguredVerificationAdapter(settings))
    client = TestClient(app)
    registration = client.post("/api/auth/register", json={
        "email": f"neatlogs-smoke-{uuid4().hex[:12]}@example.test",
        "password": "controlled-test-passphrase-12345"})
    assert registration.status_code == 201, registration.status_code
    headers = {"X-CSRF-Token": registration.json()["csrf_token"]}
    project = client.post("/api/projects", json={"name": "Controlled BOLA smoke"}, headers=headers)
    assert project.status_code == 201, project.status_code
    project_id = project.json()["id"]
    uploaded = client.post(f"/api/projects/{project_id}/upload",
                           headers={**headers, "Content-Type": "application/zip"}, content=archive())
    assert uploaded.status_code == 200, uploaded.status_code
    finding = {"target_app_id": project_id, "finding": {
        "id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
        "severity": "HIGH", "file_path": "app/access.py", "description": "Controlled test finding"}}
    submitted = client.post("/api/findings", json=finding, headers=headers)
    assert submitted.status_code == 202, submitted.status_code
    job_id = submitted.json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    assert patch["policy_status"] == "PASSED"
    assert client.post(f"/api/jobs/{job_id}/verify", headers=headers).status_code == 409
    approved = client.post(f"/api/jobs/{job_id}/approval", headers=headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert approved.status_code == 200, approved.status_code
    verified = client.post(f"/api/jobs/{job_id}/verify", headers=headers)
    assert verified.status_code == 200, verified.status_code
    assert verified.json()["status"] == "VERIFIED"
    assert verified.json()["tests_passed"] == 8 and verified.json()["tests_failed"] == 0

    telemetry = app.state.workflow.telemetry
    queue_drained = telemetry.wait_for_queue(10)
    import neatlogs
    flushed = neatlogs.flush(timeout_millis=10_000)
    diagnostics = neatlogs.get_delivery_diagnostics()
    events = list(telemetry.local_events)
    order = [event["event"] for event in events]
    expected = ["project.uploaded", "finding.submitted", "agent.inference.started",
                "agent.inference.completed", "patch.generated", "patch.validation.completed",
                "approval.recorded", "verification.started", "verification.completed"]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "workflow_status": verified.json()["status"],
        "tests_passed": verified.json()["tests_passed"],
        "tests_failed": verified.json()["tests_failed"],
        "sdk_version": neatlogs.__version__,
        "queue_drained": queue_drained, "sdk_flush": bool(flushed),
        "sdk_captured": telemetry.sent, "exporter_dropped": telemetry.dropped,
        "failure_category": telemetry.failure_category,
        "sdk_span_export_failures": diagnostics["span_export_failures"],
        "sdk_span_queue_drops": diagnostics["span_queue_drops"],
        "sdk_masked_span_drops": diagnostics["masked_span_drops"],
        "sdk_mask_counts": dict(MASK_COUNTS),
        "event_order": order,
        "exact_nine": order == expected and set(order) == EVENT_NAMES,
        "correlation_consistent": len({event["correlation_id"] for event in events}) == 1,
        "correlation_id": events[0]["correlation_id"] if events else None,
        "trace_ids": list(telemetry.trace_ids),
        "metadata": events,
    }
    (evidence_root / "delivery.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"metadata"}}, indent=2))
    print("evidence_file", evidence_root / "delivery.json")
    return 0 if report["exact_nine"] and report["sdk_flush"] and not report["sdk_span_export_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

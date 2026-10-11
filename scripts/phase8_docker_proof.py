"""Fixture-labeled B/C integration proof with fresh owned uploads and real Docker."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app
from backend.schemas import AgentProposal
from backend.services.verification_adapter import ConfiguredVerificationAdapter

ROOT = Path(__file__).resolve().parents[1]


class FixtureAgent:
    def __init__(self, name: str):
        self.name = name

    def propose_patch(self, finding, source_context, attempt, feedback=None):
        return AgentProposal(root_cause="fixture BOLA finding", explanation="controlled fixture proof",
                             patch_format="unified_diff",
                             patch_text=(ROOT / "verification/fixtures" / self.name).read_text(),
                             files_changed=["app/access.py"])


def run_case(name: str, expected: str) -> dict:
    from backend.tests.test_product import archive
    token = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    settings = Settings(database_path=ROOT / "local-audit" / f"phase8-{name}-{token}.db",
                        source_root=ROOT / "verification/lab",
                        protected_tests_root=ROOT / "verification/protected_tests",
                        project_root=ROOT / "local-audit" / f"phase8-projects-{token}",
                        verifier_callable="verification.adapter:verify_backend_patch",
                        verifier_timeout_seconds=120)
    client = TestClient(create_app(settings, FixtureAgent(name), ConfiguredVerificationAdapter(settings)))
    register = client.post("/api/auth/register", json={"email": f"proof-{token}@example.test",
                                                     "password": "local-proof-passphrase-12345"})
    assert register.status_code == 201, register.text
    headers = {"X-CSRF-Token": register.json()["csrf_token"]}
    project = client.post("/api/projects", json={"name": "Phase 8 fixture proof"}, headers=headers).json()
    lab = ROOT / "verification/lab/app"
    payload = archive({"requirements.txt": "fastapi==0.143.0\n", "app/__init__.py": "",
                       "app/access.py": (lab / "access.py").read_bytes(),
                       "app/sample_data.py": (lab / "sample_data.py").read_bytes()})
    upload = client.post(f"/api/projects/{project['id']}/upload",
                         content=payload, headers={**headers, "Content-Type": "application/zip"})
    assert upload.status_code == 200, upload.text
    finding = {"target_app_id": project["id"], "finding": {"id": "BOLA-PHASE8-FIXTURE",
               "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION", "severity": "HIGH",
               "file_path": "app/access.py", "description": "Controlled BOLA fixture proof"}}
    job = client.post("/api/findings", json=finding, headers=headers)
    assert job.status_code == 202, job.text
    job_id = job.json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    approved = client.post(f"/api/jobs/{job_id}/approval", headers=headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert approved.status_code == 200, approved.text
    verified = client.post(f"/api/jobs/{job_id}/verify", headers=headers)
    assert verified.status_code == 200, verified.text
    result = verified.json()
    assert result["status"] == expected, result
    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    first = evidence["verification_runs"][0]
    return {"scenario": "B_INCOMPLETE_FIXTURE" if expected == "VERIFICATION_FAILED" else "C_CORRECT_FIXTURE",
            "executed_at": first["completed_at"], "source_revision": evidence["target_binding"]["source_revision"],
            "patch_hash": patch["patch_hash"], "profile": evidence["target_binding"]["verification_profile"],
            "tests_total": result["tests_total"], "tests_passed": result["tests_passed"],
            "tests_failed": result["tests_failed"], "docker_execution": "completed" if result["execution_completed"] else "incomplete",
            "evidence_id": first["id"], "job_id": job_id, "verdict": result["status"],
            "fixture_based": True, "database": str(settings.database_path.relative_to(ROOT))}


def main() -> None:
    for name, expected in (("incomplete_patch.diff", "VERIFICATION_FAILED"),
                           ("correct_patch.diff", "VERIFIED")):
        print(json.dumps(run_case(name, expected), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

"""Browser session, project ownership, ZIP policy and approval integration tests."""
from io import BytesIO
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient
import pytest

from backend.config import Settings
from backend.main import create_app
from backend.tests.conftest import FakeAgent, FakeVerifier

ROOT = Path(__file__).resolve().parents[2]


def archive(entries):
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for name, contents in entries.items():
            output.writestr(name, contents)
    return stream.getvalue()


@pytest.fixture
def product(tmp_path):
    settings = Settings(database_path=tmp_path / "product.db",
                        source_root=ROOT / "verification" / "lab",
                        protected_tests_root=ROOT / "verification" / "protected_tests",
                        project_root=tmp_path / "projects", operator_token="")
    app = create_app(settings, FakeAgent(), FakeVerifier())
    return app


def register(app, email):
    client = TestClient(app)
    result = client.post("/api/auth/register", json={"email": email, "password": "safe-passphrase-12345"})
    assert result.status_code == 201, result.text
    return client, {"X-CSRF-Token": result.json()["csrf_token"]}


def test_session_registration_login_logout_and_csrf(product):
    client, headers = register(product, "alice@example.test")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    headers = {"X-CSRF-Token": me.json()["csrf_token"]}
    assert client.post("/api/projects", json={"name": "A"}).status_code == 403
    assert client.post("/api/projects", json={"name": "A"}, headers=headers).status_code == 201
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.test", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.test", "password": "safe-passphrase-12345"}).status_code == 200


def test_project_isolation_upload_and_finding(product):
    alice, ah = register(product, "alice@example.test")
    bob, bh = register(product, "bob@example.test")
    response = alice.post("/api/projects", json={"name": "Uploaded BOLA"}, headers=ah)
    project_id = response.json()["id"]
    assert bob.get(f"/api/projects/{project_id}").status_code == 404
    assert bob.post(f"/api/projects/{project_id}/upload", headers={**bh, "Content-Type": "application/zip"}, content=b"anything").status_code == 404
    lab = ROOT / "verification" / "lab" / "app"
    data = archive({"requirements.txt": "fastapi==0.143.0\n", "app/__init__.py": "",
                    "app/access.py": (lab / "access.py").read_bytes(),
                    "app/sample_data.py": (lab / "sample_data.py").read_bytes()})
    result = alice.post(f"/api/projects/{project_id}/upload", headers={**ah, "Content-Type": "application/zip"}, content=data)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "SUPPORTED_BOLA_CONTRACT"
    assert "app/access.py" in alice.get(f"/api/projects/{project_id}/files").json()
    finding = {"target_app_id": project_id, "finding": {"id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
               "severity": "HIGH", "file_path": "app/access.py", "description": "Authorized finding"}}
    job = alice.post("/api/findings", json=finding, headers=ah)
    assert job.status_code == 202, job.text
    job_id = job.json()["job_id"]
    assert bob.get(f"/api/jobs/{job_id}").status_code == 404
    assert bob.get(f"/api/jobs/{job_id}/evidence").status_code == 404
    assert all(item["id"] != job_id for item in bob.get("/api/jobs").json())
    assert alice.get(f"/api/jobs/{job_id}").status_code == 200


@pytest.mark.parametrize("entries", [
    {}, {"../escape.py": "bad"}, {"/absolute.py": "bad"},
    {"app/access.py": "A" * (2 * 1024 * 1024 + 1)},
])
def test_malicious_zip_rejected(product, entries):
    client, headers = register(product, "alice@example.test")
    project_id = client.post("/api/projects", json={"name": "bad"}, headers=headers).json()["id"]
    result = client.post(f"/api/projects/{project_id}/upload", headers={**headers, "Content-Type": "application/zip"}, content=archive(entries))
    assert result.status_code == 422
    assert not (product.state.workflow.settings.project_root / project_id / "source").exists()

@pytest.mark.docker
@pytest.mark.parametrize("fixture_name,expected", [("correct_patch.diff", "VERIFIED"),
                                            ("incomplete_patch.diff", "VERIFICATION_FAILED")])
def test_uploaded_project_real_docker_verification(tmp_path, fixture_name, expected):
    from backend.services.verification_adapter import ConfiguredVerificationAdapter
    from backend.schemas import AgentProposal
    class FixtureAgent:
        def propose_patch(self, finding, source_context, attempt, feedback=None):
            patch = (ROOT / "verification" / "fixtures" / fixture_name).read_text()
            return AgentProposal(root_cause="fixture security finding", explanation="fixture patch",
                                 patch_format="unified_diff", patch_text=patch,
                                 files_changed=["app/access.py"])
    settings = Settings(database_path=tmp_path / "product.db",
                        source_root=ROOT / "verification" / "lab",
                        protected_tests_root=ROOT / "verification" / "protected_tests",
                        project_root=tmp_path / "projects", operator_token="",
                        verifier_callable="verification.adapter:verify_backend_patch",
                        verifier_timeout_seconds=120)
    app = create_app(settings, FixtureAgent(), ConfiguredVerificationAdapter(settings))
    client, headers = register(app, "alice@example.test")
    project_id = client.post("/api/projects", json={"name": "BOLA lab"}, headers=headers).json()["id"]
    lab = ROOT / "verification" / "lab" / "app"
    data = archive({"requirements.txt": "fastapi==0.143.0\n", "app/__init__.py": "",
                    "app/access.py": (lab / "access.py").read_bytes(),
                    "app/sample_data.py": (lab / "sample_data.py").read_bytes()})
    result = client.post(f"/api/projects/{project_id}/upload", headers={**headers, "Content-Type": "application/zip"}, content=data)
    assert result.status_code == 200, result.text
    finding = {"target_app_id": project_id, "finding": {"id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
               "severity": "HIGH", "file_path": "app/access.py", "description": "Authorized finding"}}
    job_id = client.post("/api/findings", json=finding, headers=headers).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    assert patch["policy_status"] == "PASSED"
    assert client.post(f"/api/jobs/{job_id}/verify", headers=headers).status_code == 409
    approval = client.post(f"/api/jobs/{job_id}/approval", headers=headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert approval.status_code == 200, approval.text
    verification = client.post(f"/api/jobs/{job_id}/verify", headers=headers)
    assert verification.status_code == 200, verification.text
    assert verification.json()["status"] == expected, verification.text
    assert verification.json()["tests_passed"] == (8 if expected == "VERIFIED" else 5)
    assert verification.json()["tests_failed"] == (0 if expected == "VERIFIED" else 3)
    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert evidence["verification_runs"][0]["result"]["tests_total"] == 8
    assert len(evidence["verification_runs"][0]["result"]["test_results"]) == 8
    assert evidence["verification_runs"][0]["attestation_integrity"] == "VALID"
    assert evidence["conclusion"] == ("VERIFIED" if expected == "VERIFIED" else "NOT_VERIFIED")


def test_session_expiration(product):
    client, headers = register(product, "expiry@example.test")
    with product.state.workflow.db.transaction() as db:
        db.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"name": "expired"}, headers=headers).status_code == 401


def test_corrupt_duplicate_symlink_and_unsupported_archives(product):
    import stat
    client, headers = register(product, "archive@example.test")
    def new_project():
        return client.post("/api/projects", json={"name": "archive"}, headers=headers).json()["id"]
    project_id = new_project()
    assert client.post(f"/api/projects/{project_id}/upload", headers={**headers, "Content-Type": "application/zip"}, content=b"corrupt").status_code == 422
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        output.writestr("same.py", "a")
        output.writestr("same.py", "b")
    assert client.post(f"/api/projects/{new_project()}/upload", headers={**headers, "Content-Type": "application/zip"}, content=stream.getvalue()).status_code == 422
    link = zipfile.ZipInfo("app/access.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        output.writestr(link, "../../secret")
    assert client.post(f"/api/projects/{new_project()}/upload", headers={**headers, "Content-Type": "application/zip"}, content=stream.getvalue()).status_code == 422
    unsupported = client.post(f"/api/projects/{new_project()}/upload", headers={**headers, "Content-Type": "application/zip"}, content=archive({"main.js": "console.log('hello')"}))
    assert unsupported.status_code == 200
    assert unsupported.json()["status"] == "UNSUPPORTED"


def test_oversized_archive_rejected(product):
    client, headers = register(product, "large@example.test")
    project_id = client.post("/api/projects", json={"name": "large"}, headers=headers).json()["id"]
    response = client.post(f"/api/projects/{project_id}/upload",
                           headers={**headers, "Content-Type": "application/zip"},
                           content=b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 422
    assert not (product.state.workflow.settings.project_root / project_id / "source").exists()

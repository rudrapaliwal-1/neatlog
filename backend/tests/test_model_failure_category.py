"""The user-visible audit must classify provider failures without leaking details."""
from fastapi.testclient import TestClient
from agent.generator import GenerationError
from backend.config import Settings
from backend.main import create_app
from backend.tests.conftest import FakeVerifier


class FailingAgent:
    def propose_patch(self, finding, source_context, attempt, feedback=None):
        raise GenerationError("secret source or prompt must remain local", "ProviderTimeoutError")


def test_model_failure_is_categorized_without_leaking_payload(tmp_path):
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    settings = Settings(database_path=tmp_path / "failure.db", source_root=root / "verification/lab",
                        protected_tests_root=root / "verification/protected_tests",
                        operator_token="local-demo-token-0123456789-0123456789")
    client = TestClient(create_app(settings, FailingAgent(), FakeVerifier()),
                        headers={"X-Operator-Token": settings.operator_token})
    result = client.post("/api/findings", json={"target_app_id": "bola-demo-v1", "finding": {
        "id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION", "severity": "HIGH",
        "file_path": "app/access.py", "description": "authorized BOLA finding"}})
    assert result.status_code == 202
    events = client.get(f"/api/jobs/{result.json()['job_id']}/events").json()
    assert events[-1]["event"]["reason"] == "planner integration failed (ProviderTimeoutError)"
    assert "secret source" not in str(events)

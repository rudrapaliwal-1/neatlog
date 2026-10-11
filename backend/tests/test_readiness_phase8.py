from backend.readiness import probe
from backend.services.agent_adapter import ConfiguredAgentAdapter
from backend.services.verification_adapter import ConfiguredVerificationAdapter
from backend.config import Settings
from backend.database import Database
from backend.workflow import Workflow


def test_bounded_readiness_fails_closed_and_sanitizes_diagnostics(tmp_path, monkeypatch):
    source = tmp_path / "source"
    tests = tmp_path / "tests"
    source.mkdir()
    tests.mkdir()
    settings = Settings(database_path=tmp_path / "ready.db", source_root=source,
                        project_root=tmp_path / "projects", protected_tests_root=tests,
                        agent_callable="agent.planner:propose_patch",
                        verifier_callable="verification.adapter:verify_backend_patch")
    workflow = Workflow(Database(settings.database_path), settings,
                        ConfiguredAgentAdapter(settings), ConfiguredVerificationAdapter(settings))
    def no_network(*args, **kwargs):
        raise RuntimeError("SECRET_NEVER_RETURN_THIS")
    monkeypatch.setattr("backend.readiness.urlopen", no_network)
    monkeypatch.setattr("backend.readiness.shutil.which", lambda name: None)
    result = probe(workflow)
    assert result["status"] == "not_ready"
    assert result["checks"]["ollama"]["status"] == "unavailable"
    assert result["checks"]["docker"]["status"] == "unavailable"
    assert result["checks"]["verifier_image"]["status"] == "unavailable"
    assert result["checks"]["patch_utility"]["status"] == "unavailable"
    assert "SECRET_NEVER_RETURN_THIS" not in str(result)

"""Planner/backend integration without pretending mocked inference is real."""
from unittest.mock import patch

import pytest

from backend.config import Settings
from backend.schemas import AgentProposal
from backend.services.agent_adapter import ConfiguredAgentAdapter, load_callable
from agent.planner import PlannerError, propose_patch
from agent.reflection import InvalidRevisionFeedback


DIFF = """diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
@@ -1 +1 @@
-return document
+return document if owner else None
"""
FINDING = {"id": "BOLA-001", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
           "severity": "HIGH", "file_path": "app/access.py",
           "description": "An owner check is missing."}
SOURCE = {"app/access.py": "return document\n"}
FEEDBACK = {"tests_total": 8, "tests_failed": 1,
            "failed_tests": ["test_security::test_non_owner_access"]}
PROPOSAL = {"root_cause": "missing owner check", "explanation": "require ownership",
            "patch_format": "unified_diff", "patch_text": DIFF,
            "files_changed": ["app/access.py"], "model": "qwen2.5-coder:7b", "attempt": 0}


class FakeObserver:
    def __init__(self):
        self.events = []

    def workflow(self, **metadata):
        from contextlib import nullcontext
        return nullcontext()

    def event(self, event, **metadata):
        self.events.append(event.value)
        return True


def test_backend_can_load_exact_planner_path(tmp_path):
    assert load_callable("agent.planner:propose_patch", "agent") is propose_patch
    settings = Settings(database_path=tmp_path / "db", source_root=tmp_path,
                        agent_callable="agent.planner:propose_patch")
    with patch("agent.planner.generate_patch", return_value=PROPOSAL):
        result = ConfiguredAgentAdapter(settings).propose_patch(FINDING, SOURCE, 0, None)
    assert isinstance(result, AgentProposal)
    assert set(result.model_dump()) == set(AgentProposal.model_fields)


def test_revision_uses_bounded_guidance_and_returns_exact_schema():
    observer = FakeObserver()
    with (patch("agent.planner._observer", return_value=observer),
          patch("agent.planner.generate_patch", return_value=PROPOSAL) as generate):
        result = propose_patch(FINDING, SOURCE, 1, FEEDBACK)
    assert set(result) == set(AgentProposal.model_fields)
    assert "1 of 8 tests failed" in generate.call_args.args[3]
    assert "revision_requested" in observer.events
    assert "revised_patch_generated" in observer.events


@pytest.mark.parametrize("attempt,feedback", [(0, FEEDBACK), (1, None), (2, {}), (3, FEEDBACK), (True, None)])
def test_planner_rejects_invalid_attempt_or_feedback(attempt, feedback):
    with pytest.raises((PlannerError, InvalidRevisionFeedback)):
        propose_patch(FINDING, SOURCE, attempt, feedback)


def test_planner_never_sends_unauthorized_source_to_provider():
    with patch("agent.planner.generate_patch") as generate:
        with pytest.raises(Exception):
            propose_patch(FINDING, {"tests/secret.py": "do not read"}, 0)
    generate.assert_not_called()


def test_provider_failure_is_redacted_and_observed():
    observer = FakeObserver()
    with (patch("agent.planner._observer", return_value=observer),
          patch("agent.planner.generate_patch", side_effect=RuntimeError("private source"))):
        with pytest.raises(RuntimeError):
            propose_patch(FINDING, SOURCE, 0)
    assert "provider_error" in observer.events
    assert "patch_generated" not in observer.events


def test_provider_timeout_is_observed():
    observer = FakeObserver()
    with (patch("agent.planner._observer", return_value=observer),
          patch("agent.planner.generate_patch", side_effect=TimeoutError("timeout"))):
        with pytest.raises(TimeoutError):
            propose_patch(FINDING, SOURCE, 0)
    assert "timeout" in observer.events


def test_rejected_model_edit_is_not_mislabeled_provider_error():
    from agent.generator import GenerationError
    observer = FakeObserver()
    with (patch("agent.planner._observer", return_value=observer),
          patch("agent.planner.generate_patch", side_effect=GenerationError("Patch generation failed (EditError)", "EditError"))):
        with pytest.raises(GenerationError):
            propose_patch(FINDING, SOURCE, 0)
    assert "patch_rejected" in observer.events
    assert "provider_error" not in observer.events


def test_provider_timeout_type_emits_timeout_event():
    from agent.generator import GenerationError
    observer = FakeObserver()
    with (patch("agent.planner._observer", return_value=observer),
          patch("agent.planner.generate_patch", side_effect=GenerationError("Patch generation failed (ProviderTimeoutError)", "ProviderTimeoutError"))):
        with pytest.raises(GenerationError):
            propose_patch(FINDING, SOURCE, 0)
    assert "timeout" in observer.events
    assert "provider_error" not in observer.events

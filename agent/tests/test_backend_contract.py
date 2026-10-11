"""Read-only contract tests against the supplied Phase 4 backend checkout.

The backend package is imported from its original path without copying or
modifying it. The test fails if that path is unavailable; it never skips.
"""

import ast
import inspect
import os
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
PHASE4_ROOT = Path(os.environ.get(
    "SENTINEL_PHASE4_ROOT",
    str(Path(__file__).resolve().parents[2]),
))
if not (PHASE4_ROOT / "backend" / "schemas.py").is_file():
    raise RuntimeError("Phase 4 backend checkout is unavailable")
sys.path.insert(0, str(PHASE4_ROOT))

from pydantic import ValidationError
from backend.config import Settings
from backend.policy import validate_patch
from backend.schemas import AgentProposal
from backend.services.agent_adapter import ConfiguredAgentAdapter
from agent.reflection import build_revision_guidance

PATCH = """diff --git a/app/access.py b/app/access.py
--- a/app/access.py
+++ b/app/access.py
@@ -1 +1 @@
-return document
+return document if owner else None
"""


def valid_proposal():
    return {
        "root_cause": "Missing owner check",
        "explanation": "Require the requesting user to own the document.",
        "patch_format": "unified_diff",
        "patch_text": PATCH,
        "files_changed": ["app/access.py"],
    }


class BackendContractTests(unittest.TestCase):
    def test_planner_callable_signature(self):
        signature = inspect.signature(ConfiguredAgentAdapter.propose_patch)
        self.assertEqual(list(signature.parameters),
                         ["self", "finding", "source_context", "attempt", "feedback"])
        self.assertIsNone(signature.parameters["feedback"].default)

    def test_exact_proposal_schema_and_authorized_policy(self):
        self.assertEqual(set(AgentProposal.model_fields), set(valid_proposal()))
        proposal = AgentProposal.model_validate(valid_proposal())
        settings = Settings(database_path=Path("unused.db"), source_root=Path("."))
        for attempt in (0, 1, 2):
            with self.subTest(attempt=attempt):
                result = validate_patch("bola-demo-v1", proposal.patch_text,
                                        proposal.files_changed, attempt, settings)
                self.assertTrue(result.allowed, result.reasons)
        self.assertFalse(validate_patch("bola-demo-v1", proposal.patch_text,
                                        proposal.files_changed, 3, settings).allowed)

    def test_schema_rejects_mismatched_proposals(self):
        for mutation in (
            lambda p: p.pop("root_cause"),
            lambda p: p.update(patch_format="plain_text"),
            lambda p: p.update(files_changed="app/access.py"),
            lambda p: p.update(approved=True),
            lambda p: p.update(patch_text=""),
        ):
            payload = valid_proposal()
            mutation(payload)
            with self.subTest(payload_keys=tuple(payload)), self.assertRaises(ValidationError):
                AgentProposal.model_validate(payload)

    def test_policy_rejects_bad_diff_or_declared_files(self):
        settings = Settings(database_path=Path("unused.db"), source_root=Path("."))
        for patch, files in ((PATCH, ["tests/test_security.py"]),
                             (PATCH.replace("app/access.py", "tests/test_security.py"),
                              ["tests/test_security.py"]),
                             ("not a unified diff", ["app/access.py"])):
            with self.subTest(files=files):
                self.assertFalse(validate_patch("bola-demo-v1", patch, files,
                                                1, settings).allowed)

    def test_backend_constructs_exact_retry_feedback_fields(self):
        tree = ast.parse((PHASE4_ROOT / "backend" / "workflow.py").read_text())
        feedback_dicts = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "feedback"
                    for target in node.targets)
            and isinstance(node.value, ast.Dict)
        ]
        self.assertEqual(len(feedback_dicts), 1)
        self.assertEqual({key.value for key in feedback_dicts[0].keys},
                         {"tests_total", "tests_failed", "failed_tests"})

    def test_actual_retry_payload_is_accepted_by_reflection(self):
        # backend/workflow.py constructs exactly these three fields and calls
        # the planner at backend-assigned attempt 1 or 2.
        feedback = {"tests_total": 8, "tests_failed": 1,
                    "failed_tests": ["test_security::test_non_owner_access"]}
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                guidance = build_revision_guidance(feedback, attempt)
                self.assertIn("1 of 8 tests failed", guidance)
                self.assertIn("normal backend validation", guidance)


if __name__ == "__main__":
    unittest.main()

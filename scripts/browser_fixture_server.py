"""Isolated browser acceptance-test server. Prepared patch; actual Docker verifier.

This server is never used by the live frontend at port 5173.
The token is public test data, not a live operator credential.
"""
from pathlib import Path
from backend.config import Settings
from backend.main import create_app
from backend.schemas import AgentProposal

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "browser-fixture-test-token-0123456789abcdef"


class FixtureAgent:
    def propose_patch(self, finding, source_context, attempt, feedback=None):
        return AgentProposal(root_cause="Missing ownership validation (prepared test fixture)",
                             explanation="Prepared fixture patch; verification runs in real Docker.",
                             patch_format="unified_diff",
                             patch_text=(ROOT / "verification/fixtures/correct_patch.diff").read_text(),
                             files_changed=["app/access.py"])


app = create_app(Settings(database_path=ROOT / "local-audit/browser-fixture.db",
                          source_root=ROOT / "verification/lab",
                          protected_tests_root=ROOT / "verification/protected_tests",
                          operator_token=TOKEN, frontend_origin="http://localhost:5174",
                          verifier_callable="verification.adapter:verify_backend_patch"),
                 agent=FixtureAgent())

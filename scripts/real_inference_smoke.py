"""Real local Ollama proposal smoke test. Never applies or approves the patch."""
from __future__ import annotations

import json
import os
from pathlib import Path
from time import monotonic

from agent.planner import propose_patch
from backend.config import Settings
from backend.policy import patch_hash, validate_patch
from backend.schemas import AgentProposal, Finding
from backend.services.agent_adapter import bounded_source_context


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    finding = Finding.model_validate({
        "id": "BOLA-PHASE5-REAL", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
        "severity": "HIGH", "file_path": "app/access.py",
        "description": "The document access function returns records without checking that the requesting user owns the document.",
    })
    settings = Settings(database_path=root / "backend" / "sentinel-smoke.db",
                        source_root=root / "verification" / "lab",
                        protected_tests_root=root / "verification" / "protected_tests")
    context = bounded_source_context(settings, finding)
    started = monotonic()
    try:
        proposal = AgentProposal.model_validate(propose_patch(finding.model_dump(), context, 0, None))
    except Exception as exc:
        print(json.dumps({"outcome": "generation_error", "error_type": type(exc).__name__,
                          "safe_message": str(exc)[:200],
                          "duration_seconds": round(monotonic() - started, 2)}))
        return 1
    policy = validate_patch("bola-demo-v1", proposal.patch_text, proposal.files_changed, 0, settings)
    artifact = root / "local-audit" / "real-ai-proposal.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(artifact, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(proposal.model_dump(), output, ensure_ascii=False, indent=2)
    print(json.dumps({"outcome": "proposal_generated", "model": os.getenv("SENTINEL_MODEL", "qwen2.5-coder:7b"),
                      "duration_seconds": round(monotonic() - started, 2),
                      "schema_valid": True, "policy_allowed": policy.allowed,
                      "policy_reasons": list(policy.reasons),
                      "patch_hash": patch_hash(proposal.patch_text), "artifact": str(artifact)}))
    return 0 if policy.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())

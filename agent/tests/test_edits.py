import json
from pathlib import Path
import pytest
from agent.edits import EditError, build_guard_diff, parse_guard_response
from backend.config import Settings
from backend.policy import validate_patch

SOURCE = "def get_document(requesting_user_id, document_id):\n    doc = DOCUMENTS[document_id]\n\n    return dict(doc)\n"
GUARD = 'if doc["owner_id"] != requesting_user_id:\n    raise PermissionError("Access denied")'


def test_model_guard_makes_policy_valid_diff():
    raw = json.dumps({"root_cause": "missing ownership check", "explanation": "deny other owners", "guard_code": GUARD})
    _, _, guard = parse_guard_response(raw)
    diff = build_guard_diff(SOURCE, "app/access.py", guard)
    result = validate_patch("bola-demo-v1", diff, ["app/access.py"], 0, Settings(database_path=Path("/tmp/sentinel-test-edits.db"), source_root=Path("/tmp")))
    assert result.allowed, result.reasons
    assert "+    if doc[\"owner_id\"] != requesting_user_id:" in diff


@pytest.mark.parametrize("guard", [
    'import os\n' + GUARD,
    'if doc["owner_id"] == requesting_user_id:\n    raise PermissionError("wrong")',
    'if doc["owner_id"] != requesting_user_id:\n    __import__("os").system("true")',
    'if doc["owner_id"] != requesting_user_id:\n    raise RuntimeError("wrong")',
    'if doc["owner_id"] != requesting_user_id:\n    raise PermissionError(__import__("os").getcwd())',
])
def test_rejects_unsafe_or_incorrect_guard(guard):
    raw = json.dumps({"root_cause": "x", "explanation": "x", "guard_code": guard})
    with pytest.raises(EditError):
        parse_guard_response(raw)

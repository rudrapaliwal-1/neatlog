import json
import pytest
from unittest.mock import patch
from agent.context import build_context, ContextError
from agent.parser import parse_proposal, ParseError
from agent.generator import generate_patch, GenerationError

DIFF = "diff --git a/app/access.py b/app/access.py\n--- a/app/access.py\n+++ b/app/access.py\n@@ -1,2 +1,3 @@\n def read_doc(doc, user):\n+    if doc.owner_id != user.id: raise PermissionError()\n     return doc\n"
VALID = json.dumps({"root_cause":"missing ownership check","explanation":"checks ownership before return","patch_format":"unified_diff","patch_text":DIFF,"files_changed":["app/access.py"]})

def test_context_rejects_traversal():
    with pytest.raises(ContextError): build_context({}, {"../secrets": "x"}, {"../secrets"})
def test_context_rejects_secret():
    with pytest.raises(ContextError): build_context({}, {"app/access.py":"API_KEY=abc123"}, {"app/access.py"})
def test_parser_accepts_authorized_diff():
    p = parse_proposal(VALID, {"app/access.py"}); assert p.files_changed == ["app/access.py"]
def test_parser_rejects_wrong_path():
    with pytest.raises(ParseError): parse_proposal(VALID, {"app/other.py"})
def test_parser_rejects_prose_and_extra_fields():
    with pytest.raises(ParseError): parse_proposal("Here is your patch: " + VALID, {"app/access.py"})
    obj=json.loads(VALID); obj["approved"]=True
    with pytest.raises(ParseError): parse_proposal(json.dumps(obj), {"app/access.py"})
def test_parser_rejects_deleted_file():
    obj=json.loads(VALID); obj["patch_text"]=DIFF.replace("--- a/app/access.py", "--- /dev/null")
    with pytest.raises(ParseError): parse_proposal(json.dumps(obj), {"app/access.py"})
def test_generator_uses_provider_and_returns_proposal():
    source = ("def get_document(requesting_user_id, document_id):\n"
              "    doc = DOCUMENTS[document_id]\n"
              "    return dict(doc)\n")
    guard = json.dumps({"root_cause": "missing ownership check", "explanation": "reject other owners",
                        "guard_code": "if doc[\"owner_id\"] != requesting_user_id:\n    raise PermissionError(\"Access denied\")"})
    with (patch.dict("os.environ", {"SENTINEL_ALLOWED_PATHS":"app/access.py"}),
          patch("agent.generator.OllamaProvider") as provider):
        provider.return_value.model="qwen2.5-coder:7b"
        provider.return_value.generate.return_value=guard
        result=generate_patch({"target_path":"app/access.py","description":"BOLA"}, {"app/access.py":source}, 0)
    assert result["patch_text"].startswith("diff --git a/app/access.py b/app/access.py\n")
    assert "+    if doc[\"owner_id\"] != requesting_user_id:" in result["patch_text"]
    assert result["model"] == "qwen2.5-coder:7b"
def test_generator_rejects_attempt_outside_limit():
    with pytest.raises(GenerationError): generate_patch({}, {"app/access.py":"x"}, 3)

def test_parser_accepts_phase4_canonical_fixture():
    from pathlib import Path
    fixture = Path(__file__).resolve().parents[2] / "verification" / "fixtures" / "correct_patch.diff"
    obj = {"root_cause": "missing owner check", "explanation": "enforce owner check",
           "patch_format": "unified_diff", "patch_text": fixture.read_text(),
           "files_changed": ["app/access.py"]}
    assert parse_proposal(json.dumps(obj), {"app/access.py"}).files_changed == ["app/access.py"]


def test_parser_rejects_legacy_diff_without_git_header():
    obj = json.loads(VALID)
    obj["patch_text"] = obj["patch_text"].split("\n", 1)[1]
    with pytest.raises(ParseError):
        parse_proposal(json.dumps(obj), {"app/access.py"})


def test_prompt_anchors_to_actual_authorized_source_lines():
    from agent.prompts.generation import build_generation_prompt
    source = "first\nsecond\n\n    doc = DOCUMENTS[document_id]\n    return dict(doc)\n"
    prompt = build_generation_prompt({"finding": {}, "source_context": {"app/access.py": source}}, 0)
    assert '"start_line": 1' in prompt
    assert '"old_line_count": 5' in prompt
    assert '"old_lines": ["first", "second", "", "    doc = DOCUMENTS[document_id]", "    return dict(doc)"]' in prompt
    assert "including blank lines" in prompt

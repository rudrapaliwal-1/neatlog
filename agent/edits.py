"""Build a narrow unified diff from a model-authored ownership guard.

The model supplies code, while difflib computes source positions and context.
No patch is applied or executed here; backend policy and Docker verification remain authoritative.
"""
from __future__ import annotations

import ast
import difflib
import json


class EditError(ValueError):
    pass


GUARD_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "root_cause": {"type": "string"},
        "explanation": {"type": "string"},
        "guard_code": {"type": "string"},
    },
    "required": ["root_cause", "explanation", "guard_code"],
}


def _owner_lookup(node: ast.AST) -> bool:
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == "doc" and isinstance(node.slice, ast.Constant)
            and node.slice.value == "owner_id")


def _requester(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "requesting_user_id"


def parse_guard_response(raw: str) -> tuple[str, str, str]:
    if not isinstance(raw, str) or len(raw) > 3000:
        raise EditError("Model edit response is invalid or too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise EditError("Model edit response is not JSON") from None
    if not isinstance(data, dict) or set(data) != {"root_cause", "explanation", "guard_code"}:
        raise EditError("Model edit response does not match schema")
    for key, limit in (("root_cause", 1000), ("explanation", 1000), ("guard_code", 500)):
        if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > limit:
            val_info = f"len={len(data[key])}, max={limit}" if isinstance(data.get(key), str) else f"type={type(data.get(key)).__name__}"
            raise EditError(f"Model edit field '{key}' is invalid ({val_info})")
    code = data["guard_code"].strip()
    if code.startswith("```"):
        code_block_lines = code.splitlines()
        if code_block_lines[0].startswith("```"):
            code_block_lines = code_block_lines[1:]
        if code_block_lines and code_block_lines[-1].startswith("```"):
            code_block_lines = code_block_lines[:-1]
        code = "\n".join(code_block_lines).strip()
    raw_lines = [l for l in code.splitlines() if l.strip()]
    if len(raw_lines) >= 2 and raw_lines[0].lstrip().startswith("if "):
        code = raw_lines[0] + "\n" + raw_lines[1]
    if code.startswith("ifif "):
        code = "if " + code[5:]
    import re
    code = re.sub(r"PermissionError(Error)+", "PermissionError", code)
    code = re.sub(r"requesting_user_id(_id)+", "requesting_user_id", code)
    code = re.sub(r"\[\s*['\"]\[['\"]([A-Za-z0-9_]+)['\"]\]['\"]\s*\]", r"['\1']", code)
    code = re.sub(r"PermissionError\(\s*['\"]\(+['\"](.*?)['\"][\)]+['\"]\s*\)", r'PermissionError("\1")', code)
    code = re.sub(r"PermissionError\(\s*['\"]\(\s*['\"]", 'PermissionError("', code)
    code = re.sub(r"['\"]\s*\)\s*['\"]\s*\)", '")', code)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        raise EditError("Model guard is not valid Python") from None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.If):
        raise EditError("Model guard must contain one if statement")
    guard = tree.body[0]
    test = guard.test
    if (not isinstance(test, ast.Compare) or len(test.ops) != 1 or
            not isinstance(test.ops[0], ast.NotEq) or len(test.comparators) != 1 or
            not ((_owner_lookup(test.left) and _requester(test.comparators[0])) or
                 (_requester(test.left) and _owner_lookup(test.comparators[0])))):
        raise EditError("Model guard must compare document owner with requester")
    if guard.orelse or len(guard.body) != 1 or not isinstance(guard.body[0], ast.Raise):
        raise EditError("Model guard must raise on mismatched ownership")
    exc = guard.body[0].exc
    if (not isinstance(exc, ast.Call) or not isinstance(exc.func, ast.Name) or
            exc.func.id != "PermissionError" or exc.keywords or len(exc.args) > 1 or
            any(not isinstance(arg, ast.Constant) or not isinstance(arg.value, str) for arg in exc.args)):
        raise EditError("Model guard must raise PermissionError with a literal message")
    if any(not line or line[0] in ("\t", " ") and line.startswith("\t") for line in code.splitlines()[:1]):
        raise EditError("Model guard indentation is invalid")
    return data["root_cause"], data["explanation"], code


def build_guard_diff(source: str, path: str, guard_code: str) -> str:
    if not isinstance(source, str) or not source.endswith("\n"):
        raise EditError("Authorized source must end with a newline")
    lines = source.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line == "    return dict(doc)\n"]
    if len(matches) != 1 or "    doc = DOCUMENTS[document_id]\n" not in lines[:matches[0]]:
        raise EditError("Unique authorized return anchor is absent")
    code_lines = guard_code.splitlines()
    if (len(code_lines) != 2 or
            not code_lines[0].startswith("if ") or
            not code_lines[1].lstrip().startswith("raise PermissionError")):
        raise EditError("Model guard has unsupported layout")
    added = ["    " + code_lines[0].strip() + "\n", "        " + code_lines[1].strip() + "\n"]
    updated = lines[:matches[0]] + added + lines[matches[0]:]
    diff = "".join(difflib.unified_diff(lines, updated, fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
    if not diff:
        raise EditError("Model guard produced no change")
    return f"diff --git a/{path} b/{path}\n" + diff

"""Strict preliminary parser for one authorized Git unified diff.

The backend's policy parser remains the final authority on hunk counts, path
scope, patch size and approval eligibility.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedProposal:
    root_cause: str
    explanation: str
    patch_format: str
    patch_text: str
    files_changed: list[str]


_HEADER = re.compile(r"diff --git a/([^\s]+) b/([^\s]+)")
_INDEX = re.compile(r"index [0-9a-f]{4,64}\.\.[0-9a-f]{4,64}(?: [0-7]{6})?")
_HUNK = re.compile(r"@@ -\d{1,7}(?:,\d{1,7})? \+\d{1,7}(?:,\d{1,7})? @@(?: .*)?")


def validate_unified_diff(patch: str, allowed_paths: set[str]) -> list[str]:
    if not isinstance(patch, str) or not patch or not patch.endswith("\n"):
        raise ParseError("Patch must be a newline-terminated Git unified diff")
    try:
        patch_bytes = patch.encode("utf-8")
    except UnicodeEncodeError:
        raise ParseError("Patch is not valid UTF-8") from None
    if len(patch_bytes) > 32_768 or "\r" in patch or "\x00" in patch:
        raise ParseError("Patch size or encoding is invalid")
    lines = patch[:-1].split("\n")
    match = _HEADER.fullmatch(lines[0])
    if not match or match.group(1) != match.group(2):
        raise ParseError("Patch requires one canonical diff --git header")
    path = match.group(1)
    if path not in allowed_paths or any(part in ("", ".", "..") for part in path.split("/")):
        raise ParseError("Patch path is outside the authorized allowlist")
    offset = 1
    if offset < len(lines) and lines[offset].startswith("index "):
        if not _INDEX.fullmatch(lines[offset]):
            raise ParseError("Unsupported diff index metadata")
        offset += 1
    if lines[offset:offset + 2] != [f"--- a/{path}", f"+++ b/{path}"]:
        raise ParseError("Diff file headers do not match the authorized path")
    offset += 2
    hunks = 0
    while offset < len(lines):
        if not _HUNK.fullmatch(lines[offset]):
            raise ParseError("Malformed unified diff hunk header")
        hunks += 1
        offset += 1
        content_lines = 0
        while offset < len(lines) and not lines[offset].startswith("@@ "):
            line = lines[offset]
            if line.startswith("diff --git ") or not line.startswith((" ", "+", "-", "\\")):
                raise ParseError("Unsupported diff content or metadata")
            content_lines += 1
            offset += 1
        if not content_lines:
            raise ParseError("Empty diff hunk")
    if not hunks:
        raise ParseError("Unified diff has no hunk")
    return [path]


def parse_proposal(raw: str, allowed_paths: set[str]) -> ParsedProposal:
    if not isinstance(raw, str) or len(raw) > 50_000:
        raise ParseError("Model output is invalid or too large")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise ParseError("Model output is not valid JSON") from None
    required = {"root_cause", "explanation", "patch_format", "patch_text", "files_changed"}
    if not isinstance(obj, dict) or set(obj) != required:
        raise ParseError("Model output does not match the required schema")
    for key, limit in (("root_cause", 4_000), ("explanation", 8_000)):
        if not isinstance(obj[key], str) or not obj[key].strip() or len(obj[key]) > limit:
            raise ParseError("Model explanation fields are invalid")
    if obj["patch_format"] != "unified_diff":
        raise ParseError("Unsupported patch format")
    changed = validate_unified_diff(obj["patch_text"], allowed_paths)
    if obj["files_changed"] != changed:
        raise ParseError("files_changed does not match diff headers")
    return ParsedProposal(obj["root_cause"], obj["explanation"], obj["patch_format"], obj["patch_text"], changed)

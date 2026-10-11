"""Deterministic policy for the deliberately narrow MVP patch surface."""

from dataclasses import dataclass
import hashlib
import re

from .config import Settings


AUTHORIZED_TARGET = "bola-demo-v1"
ALLOWED_PATHS = frozenset({"app/access.py"})
PROTECTED_PARTS = frozenset({"tests", "test", "runner", "config", "configuration", "__pycache__"})
PROTECTED_NAMES = frozenset({"Dockerfile", "pyproject.toml", "requirements.txt", ".env"})
DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
INDEX = re.compile(r"^index [0-9a-f]{4,64}\.\.[0-9a-f]{4,64}(?: [0-7]{6})?$")
HUNK = re.compile(r"^@@ -(\d{1,7})(?:,(\d{1,7}))? \+(\d{1,7})(?:,(\d{1,7}))? @@(?: .*)?$")


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    reasons: tuple[str, ...]
    files_changed: tuple[str, ...]


def patch_hash(patch_text: str) -> str:
    return "sha256:" + hashlib.sha256(patch_text.encode("utf-8")).hexdigest()


def validate_target(target_app_id: str) -> bool:
    return target_app_id == AUTHORIZED_TARGET


def _parse_section(section: list[str], reasons: list[str]) -> str | None:
    match = DIFF_HEADER.fullmatch(section[0])
    if not match or match.group(1) != match.group(2):
        reasons.append("unsupported diff paths or operation")
        return None
    path = match.group(1)
    if (path.startswith("/") or "\\" in path or "\x00" in path or
            any(part in ("", ".", "..") for part in path.split("/"))):
        reasons.append("absolute or traversing path")
    if path in PROTECTED_NAMES or any(part in PROTECTED_PARTS for part in path.split("/")):
        reasons.append("protected path")
    if path not in ALLOWED_PATHS:
        reasons.append("path is not allowlisted")

    offset = 1
    if offset < len(section) and section[offset].startswith("index "):
        if not INDEX.fullmatch(section[offset]):
            reasons.append("unsupported diff metadata")
        offset += 1
    if section[offset:offset + 2] != ["--- a/" + path, "+++ b/" + path]:
        reasons.append("diff file headers do not match")
        return path
    offset += 2
    hunks = 0
    changed = 0
    while offset < len(section):
        header = HUNK.fullmatch(section[offset])
        if not header:
            reasons.append("invalid hunk or unsupported diff metadata")
            return path
        old_remaining = int(header.group(2) or "1")
        new_remaining = int(header.group(4) or "1")
        hunks += 1
        offset += 1
        last_was_content = False
        while offset < len(section) and not section[offset].startswith("@@ "):
            line = section[offset]
            if line == "\\ No newline at end of file" and last_was_content:
                last_was_content = False
                offset += 1
                continue
            if not line or line[0] not in (" ", "+", "-"):
                reasons.append("invalid hunk line")
                return path
            if line[0] in (" ", "-"):
                old_remaining -= 1
            if line[0] in (" ", "+"):
                new_remaining -= 1
            if line[0] in ("+", "-"):
                changed += 1
            if old_remaining < 0 or new_remaining < 0:
                reasons.append("hunk line count mismatch")
                return path
            last_was_content = True
            offset += 1
        if old_remaining or new_remaining:
            reasons.append("hunk line count mismatch")
            return path
    if not hunks or not changed:
        reasons.append("diff has no changed hunk")
    return path


def validate_patch(target_app_id: str, patch_text: str, declared_files: list[str],
                   attempt: int, settings: Settings) -> PolicyResult:
    reasons: list[str] = []
    if not validate_target(target_app_id):
        reasons.append("unauthorized target")
    if attempt < 0 or attempt > settings.max_revisions:
        reasons.append("retry budget exceeded")
    try:
        patch_bytes = patch_text.encode("utf-8")
    except UnicodeEncodeError:
        patch_bytes = b""
        reasons.append("unsupported patch encoding")
    if len(patch_bytes) > settings.max_patch_bytes:
        reasons.append("patch size exceeded")
    if ("\r" in patch_text or any((ord(char) < 32 and char not in "\t\n") or
                                  char in "\x85\u2028\u2029" for char in patch_text)):
        reasons.append("unsupported patch encoding")
    if not patch_text.endswith("\n"):
        reasons.append("diff must end with a newline")

    lines = patch_text[:-1].split("\n") if patch_text.endswith("\n") else patch_text.split("\n")
    sections = [i for i, line in enumerate(lines) if line.startswith("diff --git ")]
    files: list[str] = []
    if not sections or sections[0] != 0:
        reasons.append("expected git unified diff")
    for position, start in enumerate(sections):
        end = sections[position + 1] if position + 1 < len(sections) else len(lines)
        path = _parse_section(lines[start:end], reasons)
        if path is not None:
            files.append(path)
    if len(files) > settings.max_changed_files or len(files) != len(set(files)):
        reasons.append("changed file limit exceeded")
    if files != declared_files:
        reasons.append("declared files do not match diff")
    return PolicyResult(not reasons, tuple(dict.fromkeys(reasons)), tuple(files))

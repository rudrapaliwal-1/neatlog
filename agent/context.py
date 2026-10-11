from __future__ import annotations
import re

class ContextError(ValueError): pass

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

def _safe_relative_path(path: str) -> bool:
    if not isinstance(path, str) or not path or path.startswith(("/", "\\\\")) or "\\\\" in path:
        return False
    parts = path.split("/")
    return all(p not in ("", ".", "..") for p in parts) and not re.match(r"^[A-Za-z]:", path)

def build_context(finding: dict, source_context: dict[str, str], allowed_paths: set[str] | None = None,
                  max_total_chars: int = 24000, max_file_chars: int = 12000) -> dict:
    """Validate caller-supplied, server-authorized source. This function never reads disk."""
    if not isinstance(finding, dict) or not isinstance(source_context, dict) or not source_context:
        raise ContextError("Finding and approved source context are required")
    if len(source_context) > 8:
        raise ContextError("Too many source files")
    approved = allowed_paths if allowed_paths is not None else set(source_context)
    normalized = {}
    total = 0
    for path, content in source_context.items():
        if not _safe_relative_path(path) or path not in approved:
            raise ContextError("Source path is not authorized")
        if not isinstance(content, str) or len(content) > max_file_chars:
            raise ContextError("Source content is invalid or too large")
        # Fail closed on obvious secrets; do not silently forward them to a model.
        if any(pattern.search(content) for pattern in _SECRET_PATTERNS):
            raise ContextError("Source context appears to contain a secret; redact before inference")
        total += len(content)
        normalized[path] = content
    if total > max_total_chars:
        raise ContextError("Source context exceeds total size limit")
    allowed_finding = {}
    for key in ("id", "type", "title", "description", "severity", "rule_id", "file_path", "target_path", "source_revision"):
        value = finding.get(key)
        if value is not None:
            if not isinstance(value, (str, int, float)):
                raise ContextError("Finding contains an invalid field")
            allowed_finding[key] = str(value)[:2000]
    target = allowed_finding.get("target_path") or allowed_finding.get("file_path")
    if target and (target not in normalized or target not in approved):
        raise ContextError("Finding target is not included in authorized source context")
    return {"finding": allowed_finding, "source_context": normalized}

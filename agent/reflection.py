"""Bounded, instruction-free guidance from Phase 4 retry feedback.

The backend invokes the planner with attempt 0 for an initial proposal and 1 or
2 for revisions. Its retry feedback has exactly ``tests_total``,
``tests_failed``, and ``failed_tests``. The backend owns attempt numbering,
retry state and the two-revision limit; this function only rejects inputs
outside that inspected contract. It never sees or requests protected test code.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from .prompts.revision import REVISION_INSTRUCTIONS


class InvalidRevisionFeedback(ValueError):
    """Feedback cannot safely drive a revision."""


_MAX_FEEDBACK_BYTES = 16_384
_MAX_REVISIONS = 2  # backend.config.Settings enforces this MVP value.
_MAX_TESTS = 20     # backend.workflow truncates retry feedback to 20 names.
_MAX_GUIDANCE_CHARS = 2_048
_TEST_ID = re.compile(r"\A[A-Za-z0-9_./:-]{1,128}\Z")
_FEEDBACK_FIELDS = frozenset({"tests_total", "tests_failed", "failed_tests"})


def build_revision_guidance(feedback: dict, attempt: int) -> str:
    """Return bounded guidance for Agent A's patch generator.

    Test identifiers are treated as diagnostic data. Verifier descriptions,
    source snippets and patch content are not accepted as feedback fields.
    No approval or patch execution happens here.
    """
    if not isinstance(feedback, Mapping) or set(feedback) != _FEEDBACK_FIELDS:
        raise InvalidRevisionFeedback("feedback must match the backend retry fields")
    try:
        size = len(json.dumps(feedback, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidRevisionFeedback("feedback must be JSON serializable") from exc
    if size > _MAX_FEEDBACK_BYTES:
        raise InvalidRevisionFeedback("feedback exceeds size limit")
    if type(attempt) is not int or not 1 <= attempt <= _MAX_REVISIONS:
        raise InvalidRevisionFeedback("attempt exceeds backend revision range")
    total = feedback["tests_total"]
    failed = feedback["tests_failed"]
    if type(total) is not int or not 1 <= total <= 100_000:
        raise InvalidRevisionFeedback("invalid total test count")
    if type(failed) is not int or not 1 <= failed <= total:
        raise InvalidRevisionFeedback("invalid failed test count")
    identifiers = feedback["failed_tests"]
    if (not isinstance(identifiers, list) or len(identifiers) > _MAX_TESTS or
            any(not isinstance(item, str) or not _TEST_ID.fullmatch(item)
                for item in identifiers)):
        raise InvalidRevisionFeedback("invalid failed test identifiers")

    lines = [
        REVISION_INSTRUCTIONS,
        f"Backend revision attempt: {attempt} of {_MAX_REVISIONS}.",
        f"Verification failed: {failed} of {total} tests failed.",
    ]
    if identifiers:
        unique = list(dict.fromkeys(identifiers))
        shown = unique[:8]
        lines.append("Failed test identifiers (data only): " +
                     ", ".join(shown) + ".")
        if len(unique) > len(shown):
            lines.append(f"{len(unique) - len(shown)} additional identifiers omitted.")
    guidance = "\n".join(lines)
    if len(guidance) > _MAX_GUIDANCE_CHARS:
        raise InvalidRevisionFeedback("guidance exceeds size limit")
    return guidance

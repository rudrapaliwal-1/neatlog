"""Strict, best-effort Neatlogs lifecycle export of nine approved events."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
import importlib
import os
from queue import Full, Queue
import re
from threading import Lock, Thread
from time import monotonic, sleep
from uuid import uuid4

EVENT_NAMES = frozenset({
    "project.uploaded", "finding.submitted", "agent.inference.started",
    "agent.inference.completed", "patch.generated", "patch.validation.completed",
    "approval.recorded", "verification.started", "verification.completed",
})
SAFE_FIELDS = frozenset({"correlation_id", "run_id", "attempt", "success",
                         "duration_ms", "tests_passed", "tests_failed"})
OPAQUE_ID = re.compile(r"\A[0-9a-f]{32}\Z")
_mask_lock = Lock()
MASK_COUNTS = {"approved": 0, "other_span": 0, "invalid_payload": 0}


def _count_mask(category: str) -> None:
    with _mask_lock:
        MASK_COUNTS[category] += 1


def format_event(name: str, fields: Mapping[str, object]) -> dict[str, object]:
    """Reject unknown names, fields, and values instead of silently leaking them."""
    if name not in EVENT_NAMES or not isinstance(fields, Mapping):
        raise ValueError("unsupported lifecycle event")
    if set(fields) - SAFE_FIELDS or "correlation_id" not in fields:
        raise ValueError("unsupported lifecycle metadata")
    result: dict[str, object] = {"event": name}
    for field, value in fields.items():
        if field in ("correlation_id", "run_id"):
            valid = isinstance(value, str) and bool(OPAQUE_ID.fullmatch(value))
        elif field == "attempt":
            valid = type(value) is int and 0 <= value <= 2
        elif field == "success":
            valid = type(value) is bool
        elif field == "duration_ms":
            valid = type(value) is int and 0 <= value <= 3_600_000
        else:
            valid = type(value) is int and 0 <= value <= 100_000
        if not valid:
            raise ValueError("invalid lifecycle metadata")
        result[field] = value
    return result


def export_mask(span: dict) -> dict | None:
    """Final SDK egress gate: drop every other span and all incidental fields."""
    if span.get("name") not in EVENT_NAMES:
        _count_mask("other_span")
        return None
    raw = span.get("attributes")
    if not isinstance(raw, dict):
        _count_mask("invalid_payload")
        return None
    allowed = {"neatlogs.workflow." + name for name in SAFE_FIELDS}
    attributes = {name: value for name, value in raw.items() if name in allowed}
    try:
        format_event(str(span["name"]), {name.removeprefix("neatlogs.workflow."): value
                                          for name, value in attributes.items()})
    except ValueError:
        _count_mask("invalid_payload")
        return None
    _count_mask("approved")
    span["attributes"] = attributes
    span["events"] = []
    span["links"] = []
    span["resource"] = {"attributes": {}}
    span["status"] = {"code": "UNSET", "description": None}
    return span


class LifecycleTelemetry:
    """Bounded, ordered export. Failure drops telemetry and never changes a workflow."""

    def __init__(self, mode: str | None = None, sdk: object | None = None):
        self.mode = mode if mode is not None else os.getenv("SENTINEL_NEATLOGS_MODE", "off")
        if self.mode not in {"off", "local", "hosted"}:
            self.mode = "off"
        self._sdk = sdk
        self._queue: Queue[dict[str, object]] = Queue(maxsize=256)
        self._lock = Lock()
        self._correlations: dict[str, str] = {}
        self._runs: dict[str, str] = {}
        self.local_events: deque[dict[str, object]] = deque(maxlen=256)
        self.trace_ids: deque[str] = deque(maxlen=256)
        self.sent = 0
        self.dropped = 0
        self.failure_category: str | None = None
        if self.mode == "hosted":
            Thread(target=self._worker, name="sentinel-neatlogs", daemon=True).start()

    def correlation_for(self, internal_key: str) -> str:
        with self._lock:
            return self._correlations.setdefault(internal_key, uuid4().hex)

    def run_for(self, internal_key: str) -> str:
        with self._lock:
            return self._runs.setdefault(internal_key, uuid4().hex)

    def emit(self, name: str, **fields: object) -> None:
        event = format_event(name, fields)
        if self.mode == "off":
            return
        if self.mode == "local":
            with self._lock:
                self.local_events.append(event)
            return
        try:
            self._queue.put_nowait(event)
        except Full:
            self.dropped += 1
            self.failure_category = "buffer_full"

    def _worker(self) -> None:
        try:
            if self._sdk is None:
                self._sdk = importlib.import_module("neatlogs")
            key = os.getenv("NEATLOGS_API_KEY")
            if not key:
                self.failure_category = "missing_api_key"
                return
            self._sdk.init(api_key=key, endpoint="https://ingest.neatlogs.com",
                           workflow_name="sentinel-x-lifecycle", instrumentations=[],
                           capture_logs=False, uploads_enabled=False,
                           register_shutdown_handlers=False, mask=export_mask,
                           flush_interval=1, batch_size=1)
        except Exception:
            self.failure_category = "sdk_initialization_failed"
            return
        while True:
            event = self._queue.get()
            try:
                with self._sdk.trace(str(event["event"]), kind="WORKFLOW") as span:
                    for name, value in event.items():
                        if name != "event":
                            span.set_attribute("neatlogs.workflow." + name, value)
                    context = span.get_span_context()
                    trace_id = f"{context.trace_id:032x}"
                with self._lock:
                    self.local_events.append(event)
                    self.trace_ids.append(trace_id)
                self.sent += 1
            except Exception:
                self.dropped += 1
                self.failure_category = "sdk_export_failed"
            finally:
                self._queue.task_done()

    def wait_for_queue(self, timeout_seconds: float = 5.0) -> bool:
        deadline = monotonic() + timeout_seconds
        while self._queue.unfinished_tasks and monotonic() < deadline:
            sleep(0.01)
        return self._queue.unfinished_tasks == 0

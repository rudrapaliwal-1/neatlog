"""Adapter for the documented Neatlogs Python SDK API.

Reference: https://docs.neatlogs.com/sdk/python (accessed 2026-10-10).
The SDK is optional at import time. A missing key disables export explicitly.
Telemetry failures must never change patch generation or approval behavior.
"""

from __future__ import annotations

import importlib
import os
import re
from contextlib import contextmanager
from enum import Enum
from typing import Iterator


class AgentEvent(str, Enum):
    CONTEXT_PREPARATION = "context_preparation"
    PROVIDER_SELECTION = "provider_selection"
    INFERENCE_STARTED = "inference_started"
    INFERENCE_COMPLETED = "inference_completed"
    PATCH_GENERATED = "patch_generated"
    PATCH_REJECTED = "patch_rejected"
    REVISION_REQUESTED = "revision_requested"
    REVISED_PATCH_GENERATED = "revised_patch_generated"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


_SAFE_ID = re.compile(r"\A[A-Za-z0-9_.:-]{1,80}\Z")


def _safe_id(value: object) -> str | None:
    return value if isinstance(value, str) and _SAFE_ID.fullmatch(value) else None


class NeatlogsObserver:
    """Emit fixed event names and allowlisted correlation metadata only.

    ``available`` says whether the SDK initialized, not whether export was
    delivered. Dashboard delivery requires credentials and a live probe.
    """

    def __init__(self, *, sdk: object | None = None, api_key: str | None = None):
        key = api_key if api_key is not None else os.environ.get("NEATLOGS_API_KEY")
        self.available = False
        self.blocker: str | None = None
        self._sdk = None
        if not key:
            self.blocker = "NEATLOGS_API_KEY is unavailable"
            return
        try:
            package = sdk if sdk is not None else importlib.import_module("neatlogs")
            package.init(
                api_key=key,
                workflow_name="security-patch-generation",
                capture_logs=False,
            )
            self._sdk = package
            self.available = True
        except Exception:
            # Never expose an SDK exception: it could include key or payload.
            self.blocker = "Neatlogs SDK import or initialization failed"

    @contextmanager
    def workflow(
        self, *, job_id: str | None = None,
        attempt: int | None = None, model_id: str | None = None,
    ) -> Iterator["NeatlogsObserver"]:
        """Group an attempt's events into one WORKFLOW trace if available."""
        if not self.available:
            yield self
            return
        try:
            trace = self._sdk.trace("security_patch_generation", kind="WORKFLOW")
            span = trace.__enter__()
            self._attributes(span, job_id, attempt, model_id)
        except Exception:
            self.blocker = "Neatlogs workflow capture failed"
            yield self
            return
        try:
            yield self
        except BaseException as exc:
            try:
                trace.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                self.blocker = "Neatlogs workflow capture failed"
            raise
        else:
            try:
                trace.__exit__(None, None, None)
            except Exception:
                self.blocker = "Neatlogs workflow capture failed"

    def event(
        self, event: AgentEvent, *, job_id: str | None = None,
        attempt: int | None = None, model_id: str | None = None,
    ) -> bool:
        """Record an event; return False if telemetry is unavailable/fails."""
        if not isinstance(event, AgentEvent) or not self.available:
            return False
        data = self._data(job_id, attempt, model_id)
        try:
            # log() is captured only in a trace. A nested trace also allows
            # callers to emit an isolated event without workflow().
            with self._sdk.trace(event.value, kind="CHAIN") as span:
                self._attributes(span, job_id, attempt, model_id)
                self._sdk.log(event.value, **data)
            return True
        except Exception:
            self.blocker = "Neatlogs event capture failed"
            return False

    @staticmethod
    def _data(job_id: object, attempt: object, model_id: object) -> dict:
        data = {}
        if safe_job := _safe_id(job_id):
            data["job_id"] = safe_job
        if type(attempt) is int and 0 <= attempt <= 1_000:
            data["attempt"] = attempt
        if safe_model := _safe_id(model_id):
            data["model_id"] = safe_model
        return data

    @classmethod
    def _attributes(cls, span: object, job_id: object, attempt: object, model_id: object) -> None:
        for key, value in cls._data(job_id, attempt, model_id).items():
            span.set_attribute(f"sentinel_x.{key}", value)

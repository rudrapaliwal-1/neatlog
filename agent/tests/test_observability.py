import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from agent.observability import AgentEvent, NeatlogsObserver


class FakeSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class FakeSDK:
    def __init__(self, fail=False):
        self.fail = fail
        self.init_args = None
        self.spans = []
        self.logs = []

    def init(self, **kwargs):
        if self.fail:
            raise RuntimeError("secret-key-in-exception")
        self.init_args = kwargs

    @contextmanager
    def trace(self, name, *, kind):
        span = FakeSpan()
        self.spans.append((name, kind, span))
        yield span

    def log(self, message, **data):
        if self.fail:
            raise RuntimeError("secret-key-in-exception")
        self.logs.append((message, data))


class ObservabilityTests(unittest.TestCase):
    def test_missing_credentials_disable_capture(self):
        with patch.dict(os.environ, {}, clear=True):
            observer = NeatlogsObserver(sdk=FakeSDK())
        self.assertFalse(observer.available)
        self.assertEqual(observer.blocker, "NEATLOGS_API_KEY is unavailable")
        self.assertFalse(observer.event(AgentEvent.TIMEOUT))

    def test_all_required_events_and_correlation(self):
        sdk = FakeSDK()
        observer = NeatlogsObserver(sdk=sdk, api_key="private-key")
        with observer.workflow(job_id="job-42", attempt=2, model_id="model.v1"):
            for event in AgentEvent:
                self.assertTrue(observer.event(event, job_id="job-42", attempt=2, model_id="model.v1"))
        self.assertEqual(len(sdk.logs), len(AgentEvent))
        self.assertEqual(sdk.spans[0][1], "WORKFLOW")
        self.assertEqual(sdk.spans[0][2].attributes["sentinel_x.job_id"], "job-42")
        self.assertTrue(all(data["attempt"] == 2 for _, data in sdk.logs))

    def test_invalid_metadata_redacted(self):
        sdk = FakeSDK()
        observer = NeatlogsObserver(sdk=sdk, api_key="private-key")
        observer.event(
            AgentEvent.PROVIDER_ERROR,
            job_id="secret=abc\nraw prompt",
            attempt=True,
            model_id="model with source code",
        )
        self.assertEqual(sdk.logs[0], ("provider_error", {}))
        self.assertNotIn("private-key", str(sdk.logs))

    def test_telemetry_failures_do_not_escape_or_expose_secrets(self):
        sdk = FakeSDK(fail=True)
        observer = NeatlogsObserver(sdk=sdk, api_key="private-key")
        self.assertFalse(observer.available)
        self.assertNotIn("private-key", observer.blocker)
        sdk = FakeSDK()
        observer = NeatlogsObserver(sdk=sdk, api_key="private-key")
        sdk.fail = True
        self.assertFalse(observer.event(AgentEvent.PROVIDER_ERROR))
        self.assertEqual(observer.blocker, "Neatlogs event capture failed")

    def test_workflow_telemetry_failure_does_not_break_generation(self):
        sdk = FakeSDK()
        observer = NeatlogsObserver(sdk=sdk, api_key="private-key")
        def failing_trace(*args, **kwargs):
            raise RuntimeError("private-key")
        sdk.trace = failing_trace
        with observer.workflow(job_id="job-42"):
            result = "generation completed"
        self.assertEqual(result, "generation completed")
        self.assertEqual(observer.blocker, "Neatlogs workflow capture failed")

    def test_unknown_event_is_not_logged(self):
        sdk = FakeSDK()
        observer = NeatlogsObserver(sdk=sdk, api_key="private-key")
        self.assertFalse(observer.event("raw user content"))
        self.assertEqual(sdk.logs, [])


if __name__ == "__main__":
    unittest.main()

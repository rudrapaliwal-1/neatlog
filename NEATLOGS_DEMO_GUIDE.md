# Neatlogs demo guide

## Modes

- `SENTINEL_NEATLOGS_MODE=off` (default): no Neatlogs SDK export.
- `SENTINEL_NEATLOGS_MODE=local`: bounded in-memory capture for tests; no network export.
- `SENTINEL_NEATLOGS_MODE=hosted`: nine-event SDK export using the existing `NEATLOGS_API_KEY` environment variable. Keep the key in the existing protected secret store or environment; never put it in a command line or report.

Install `backend/requirements.lock` into the backend environment. Start the backend normally with the desired mode and key already in its environment. No frontend action creates a Neatlogs event. The legacy Agent A observer is disabled for production planning; backend transitions emit the approved events. A Neatlogs outage can drop events but cannot alter approval, verification, or verdict.

## Repeatable controlled demonstration

After the local suite passes, run `PYTHONPATH=. /tmp/sentinel-x-py/bin/python scripts/neatlogs_hosted_smoke.py` from the project root. The script reads the existing `.env` key only into process memory, creates a fresh owned test project, uploads the supported BOLA ZIP, submits a finding, uses a known fixture patch, records an authenticated exact-hash approval, and runs the real Docker verifier. It writes a safe JSON evidence file under `local-audit/neatlogs-*/delivery.json` and prints no credential. Do not describe this fixture run as model generation. The actual Qwen-generated Phase 8 proof is in `FINAL_PHASE8_REPORT.md`.

The expected order is `project.uploaded` → `finding.submitted` → `agent.inference.started` → `agent.inference.completed` → `patch.generated` → `patch.validation.completed` → `approval.recorded` → `verification.started` → `verification.completed`. All events in one project share the same opaque correlation ID. The two verification events share one independent opaque run ID. Attempt 0 must appear. A successful final event has `success=true`, `tests_passed=8`, and `tests_failed=0` in the controlled Docker run.

To inspect hosted delivery, sign in at [Neatlogs](https://app.neatlogs.com), select the project associated with the existing SDK key, and open **Console → Traces**. Match the nine `trace_ids` from the safe evidence JSON to the trace list. Open one trace to inspect its event name and confirm there is no input/output or sensitive data. The hosted dashboard may show new traces as **Processing** before detail is finalized; wait for **Ready** before asserting retained custom metadata. The original SDK flush and local capture counters alone are not a dashboard readback.

For the latest controlled run, the [verification trace](https://app.neatlogs.com/traces) is one of the nine matched IDs. All nine matched final trace IDs reached Ready. The final trace shows `verification.completed` without input/output; open its **Attributes** panel to see the opaque correlation and run IDs, `attempt=0`, `success=true`, `tests_passed=8`, and `tests_failed=0`.

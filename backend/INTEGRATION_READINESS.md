# Phase 4 update

The Developer 3 verifier is now integrated in this checkout. See [PHASE4_INTEGRATION_REPORT.md](PHASE4_INTEGRATION_REPORT.md) for tested contract and results. The historical questions below predate integration.

# Integration readiness

The backend defines **internal** adapter contracts. Developer 3's actual verifier contract has not been supplied; these internal names are not a claim about its implementation. Keep an explicit mapping adapter in `backend/services/verification_adapter.py` when the real contract is known.

## Public API for Developer 2

All application `/api/` calls require `X-Operator-Token`; CORS preflight `OPTIONS` is exempt. The local demo token is supplied at runtime by an operator and must not be embedded in the React build. `GET /health` and `/docs` are public. The API uses exact-origin CORS from `SENTINEL_FRONTEND_ORIGIN` and `Cache-Control: no-store` for `/api/` responses.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/findings` | Ingest authorized finding; 202 `{"job_id":"job-...","status":"FINDING_RECEIVED"}`. |
| GET | `/api/jobs` | List jobs; optional `limit` 1–100 (default 100) and `offset` 0+ (default 0). |
| GET | `/api/jobs/{job_id}` | Current job, attempt, and status. |
| GET | `/api/jobs/{job_id}/patch` | Current proposal and `sha256:<64 hex>` hash for review. |
| POST | `/api/jobs/{job_id}/approval` | Body `{"patch_hash":"sha256:...","decision":"APPROVE"}` or `REJECT`. |
| POST | `/api/jobs/{job_id}/verify` | Start one trusted verification run for the approved current patch. |
| GET | `/api/jobs/{job_id}/evidence` | Full report, including `conclusion` and integrity issues. |
| GET | `/api/jobs/{job_id}/events` | Ordered audit events. |

Errors use `{"detail":"safe message","code":"STABLE_CODE"}` and appropriate HTTP status. Validation errors add an `errors` array with field locations and error types, never submitted values. 401 means missing/invalid token; 503 means no operator token is configured; 413 means body too large; 422 means invalid or unauthorized finding; 404 means missing job/patch; 409 means stale hash or invalid/replayed transition. `POST /verify` returns the result of the run just executed; an automatic retry proposal may already be awaiting approval when the response arrives.

## Developer 4: planner requirements

`SENTINEL_AGENT_CALLABLE` must point to a trusted public callable under `agent.*`, such as `agent.planner:propose_patch` only if Developer 4 provides it. The backend passes `(finding: dict, source_context: dict[str, str], attempt: int, feedback: dict | None)` and expects `AgentProposal` or an exact-schema dict with `root_cause`, `explanation`, `patch_format="unified_diff"`, `patch_text`, and `files_changed`. It provides only bounded `app/access.py` source context. Retry feedback contains test counts and sanitized failed-test identifiers. The planner must not request shell commands, approve its own patch, or claim verification. Malformed output becomes `EXECUTION_ERROR` with a sanitized event; no implicit mock is used.

Confirm with Developer 4: the actual import path, synchronous invocation or wrapper, response field names, patch syntax, exception types, maximum latency, and how failed-test feedback should be interpreted. If names differ, map them in the backend adapter rather than weakening the validated internal proposal.

## Developer 3: information needed before integration

The current internal call shape is:

```python
verify_patch(request: VerificationRequest, approval_verifier) -> VerificationResult | dict
```

`VerificationRequest` currently carries `job_id`, `target_app_id`, `patch_id`, exact stored `patch_text`, `patch_hash`, and `approval_id`. `approval_verifier(job_id, patch_id, patch_hash, approval_id) -> bool` checks the current approved patch. The backend calls the verifier only after policy pass, exact hash check, and approval lookup. The verifier must call the callback and fail closed before applying any patch. Its return is normalized into internal `status` (`PASSED`, `FAILED`, `EXECUTION_ERROR`), `tests_total`, `tests_passed`, `tests_failed`, `failed_tests`, `duration_ms`, and `execution_error`. Only a genuine `PASSED` result with at least one executed test and zero failed tests can yield `VERIFIED`.

Developer 3 needs to provide or confirm:

1. Actual Python module/callable path, sync/async behavior, request and result types, and a working example.
2. Exact field names and status values, including test counts, failures, duration, and infrastructure errors.
3. Where and when it calls the backend approval verifier; how it binds that decision to the exact patch bytes before application.
4. Target checkout location, supported diff syntax, independent path and operation checks, Docker sandbox behavior, and required regression suite.
5. How missing Docker, timeouts, partial test execution, nonzero exits, and malformed patches are reported.
6. Whether cancellation is possible when the backend timeout fires, and how duplicate calls or external side effects are prevented.
7. Safe limits and redaction for returned logs and failed-test identifiers.

Do not configure the verifier callable until these details are mapped and an integration test has exercised a real patch, approval callback, Docker run, and persisted evidence. A missing verifier transitions to `EXECUTION_ERROR`; it never returns a mock pass.

## Current state and next integration test

The backend unit suite injects fake adapters to test orchestration. The local workspace lacks the actual `agent/`, `verification/`, and authorized demo target source. After those arrive, configure the trusted import paths and source root, run one authorized finding through policy, review and approve its hash, invoke the real verifier, then inspect `/evidence` and `/events`. Include failed verification, a revised patch with fresh approval, and Docker-unavailable behavior in that integration test.

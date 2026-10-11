# Phase 6 browser API contract (authoritative Phase 5 backend)

Source: `backend/routes/*.py`, `backend/schemas.py`, `backend/workflow.py`, `backend/middleware.py`, and `backend/config.py` copied unchanged from `<local-path>` on 2026-10-10. This document describes existing endpoints; it does not add any.

## Browser security and transport

- Base origin is the backend's configured local address (documented startup uses `http://127.0.0.1:8000`). Every `/api/` request requires exactly one `X-Operator-Token` header containing the runtime operator token. The frontend must hold the token only in memory and must not put it in `VITE_*`, local storage, logs, URLs, or downloaded evidence.
- The backend CORS allowlist contains exactly `SENTINEL_FRONTEND_ORIGIN` (default `http://localhost:5173`), allows GET/POST, `Content-Type` and `X-Operator-Token`, and sets `allow_credentials=False`. Browser origin spelling must match exactly.
- All `/api/` responses set `Cache-Control: no-store` and `X-Correlation-ID`. Errors normally contain `{ "detail": "safe message", "code": "STABLE_CODE" }`; 422 request validation also has `errors: [{loc: string[], type: string}]`. Never display raw submitted secrets.
- `GET /health` and `GET /ready` are public. `/ready` returns 200 `{status:"ready"}` only when operator token and trusted callable settings are present, otherwise 503 `{status:"not_ready"}`.
- Backend policy authorizes only `target_app_id="bola-demo-v1"` and finding `file_path="app/access.py"`. The UI should present this as a predefined demo scenario. There is no general finding discovery API.

## Endpoint matrix

| Method and path | Request | 2xx response | Auth | Execution and state | Common errors |
| --- | --- | --- | --- | --- | --- |
| `POST /api/findings` | Exact `FindingRequest`: `{target_app_id:string, finding:{id:string, type:string, severity:"LOW"\|"MEDIUM"\|"HIGH"\|"CRITICAL", file_path:string, description:string}}`; no extra fields | **202** `{job_id:string,status:"FINDING_RECEIVED"}` | Token | Creates a job and schedules planner in a FastAPI background task. Poll the job; do not POST again on a slow response. | 401 auth, 413 request too large, 422 invalid or unauthorized target/path, 503 source unavailable |
| `GET /api/jobs?limit=100&offset=0` | `limit` 1–100, `offset` ≥0 | **200**, a bare array of flat job records; each contains `id,target_app_id,status,attempt,created_at,updated_at,version,finding` | Token | Read-only list, newest first. No separate findings-list endpoint. | 401, 422 invalid query |
| `GET /api/jobs/{job_id}` | No body | **200**, one flat job record as above | Token | Read-only status; poll during `FINDING_RECEIVED`/`PLANNING`. | 401, 404 `JOB_NOT_FOUND` |
| `GET /api/jobs/{job_id}/patch` | No body | **200**, current proposal with `id,job_id,attempt,root_cause,explanation,patch_format,patch_text,files_changed,patch_hash,policy_status,policy_details,created_at` | Token | Read only after a proposal exists. `patch_text` is the exact unified diff; approval must use its `patch_hash` unchanged. | 401, 404 `PATCH_NOT_FOUND` |
| `POST /api/jobs/{job_id}/approval` | Exact `{patch_hash:"sha256:<64 lowercase hex>",decision:"APPROVE"\|"REJECT"}` | **200**, `{approval_id,job_id,patch_id,attempt,patch_hash,decision,approved_by,identity_kind,source_revision,created_at}` | Token | Allowed only from `AWAITING_APPROVAL` for current policy-passed patch. APPROVE moves to `VERIFYING`; it does **not** run Docker. REJECT moves to `USER_REJECTED`. A revised patch needs a new hash and approval. | 401, 404, 409 invalid state/duplicate/stale hash (`PATCH_HASH_MISMATCH`), 422 invalid body |
| `POST /api/jobs/{job_id}/verify` | No body | **200**, `{job_id,patch_hash,status,...verification fields}`; fields include `tests_total,tests_passed,tests_failed,failed_tests,duration_ms` on a completed verifier result and may include `execution_error` on failure | Token | Requires `VERIFYING` plus active exact-hash approval. Runs Docker synchronously, potentially for minutes. If tests fail, backend may synchronously generate the next revision before returning; fetch current job and patch afterwards. Do not automatically retry POST. | 401, 404, 409 missing approval/invalid state/replay, 503 integration unavailable |
| `GET /api/jobs/{job_id}/evidence` | No body | **200**, `{job_id,finding,target_app_id,target_binding,source_revision_current,status,patch_attempts,approvals,verification_runs,failure_history,integrity_issues,conclusion,limitations}` | Token | Read-only evidence. `conclusion` is backend-computed `VERIFIED` or `NOT_VERIFIED`; render only this authoritative value. Attempts and runs include integrity annotations. | 401, 404 |
| `GET /api/jobs/{job_id}/events` | No body | **200**, bare chronological array of rows `{id,job_id,event_type,event_json,created_at,event}` | Token | Read-only audit timeline. `event` is parsed JSON with timestamp, job ID, event type, correlation ID, and event-specific fields. This is not a Neatlogs hosted trace ID. | 401, 404 |

The actual backend does **not** expose a separate `GET /api/findings`, `POST /api/jobs`, "start generation", "request revision", trace-query, or streaming endpoint. A finding POST creates the job and schedules initial generation. Revision generation is backend-managed after a failed verification, limited to attempts 1 and 2.

## States, polling, and user actions

`FINDING_RECEIVED → PLANNING → AWAITING_APPROVAL → VERIFYING → VERIFIED` is the successful route. Other states are `POLICY_REJECTED`, `USER_REJECTED`, `VERIFICATION_FAILED`, `RETRY_EXHAUSTED`, and `EXECUTION_ERROR`. `VERIFICATION_FAILED` may be transient while the backend creates a revised proposal. The browser should poll `GET /api/jobs/{job_id}` during planning, stop polling on unmount or job switch, fetch `/patch` when status reaches `AWAITING_APPROVAL`, and show an explicit approval action for that exact attempt/hash. During synchronous `POST /verify`, show an in-flight state and disable duplicate verification; after it resolves, refresh job, patch, evidence, and events. Do not infer success from HTTP 200 alone.

The planner timeout is configurable (`SENTINEL_PLANNER_TIMEOUT_SECONDS=660` in the Phase 5 example); the verifier timeout defaults to 300 seconds. The frontend must allow for these durations without automatic POST retries. Read-only GET retries may be bounded after transient network failure. Page refresh can restore a job by its ID, but the operator token must be re-entered if held only in memory.

## Error and trust boundaries

The backend rejects missing/incorrect token with 401; an unconfigured token yields 503. It rejects stale hashes, unauthorized paths, malformed proposals, invalid transitions, source revision changes, duplicate verification, and unsupported attempts server-side. The frontend may explain those results but cannot override them. The verifier alone supplies test results; the backend checks evidence bindings and computes the evidence conclusion. The client must never manufacture a `VERIFIED` label, test count, approval state, trace URL, or revision attempt.

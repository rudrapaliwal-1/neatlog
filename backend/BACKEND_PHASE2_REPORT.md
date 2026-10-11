# SENTINEL-X backend Phase 2 report

## Outcome

Hardened the existing FastAPI and SQLite backend in place. The original workflow and route paths remain. The project still needs the real planner, authorized target checkout, Developer 3's verifier contract, and an end-to-end Docker run before it can claim an operational security remediation loop. Unit tests alone do not establish production readiness.

## Files modified or added

| Area | Files |
| --- | --- |
| Configuration and HTTP boundary | `backend/config.py`, `backend/config.example.env` (new), `backend/middleware.py` (new), `backend/main.py`, `backend/schemas.py`, `backend/approvals.py` |
| Policy, persistence, workflow, adapters | `backend/policy.py`, `backend/database.py`, `backend/models.py`, `backend/workflow.py`, `backend/services/agent_adapter.py`, `backend/services/verification_adapter.py`, `backend/routes/jobs.py` |
| Tests | `backend/tests/conftest.py`, `backend/tests/test_approvals.py`, `backend/tests/test_workflow.py`, `backend/tests/test_hardening.py` (new) |
| Documentation | `backend/README.md`, `backend/.gitignore`, `backend/BACKEND_SECURITY_AUDIT.md` (new), `backend/INTEGRATION_READINESS.md` (new), this report (new) |

No frontend, agent, or verification source was changed. No GitHub operations were performed.

## Confirmed vulnerabilities and reliability gaps corrected

- All `/api/` reads and writes now require the configured local operator token (CORS preflight `OPTIONS` is exempt). The API is closed when no token is configured; health and Swagger remain public.
- Request bodies are capped before JSON parsing, and input, proposal, and verifier result schemas reject extra or malformed fields.
- The narrow unified-diff policy now checks headers, changed path, hunk syntax and counts, metadata, file operation, size, and UTF-8. Patch hashing remains exact UTF-8 SHA-256.
- Approval records now store the attempt and are checked against current job state, patch ID, attempt, hash, and recomputed patch bytes. Replay, mismatch, stale approval, and concurrent attempts are rejected.
- Dynamic import paths are restricted to reviewed public callables under `agent.*` and `verification.*`.
- SQLite uses WAL, a 30-second busy timeout, synchronous FULL, transactional state/event writes, snapshot reads, and a unique verification-run index. Audit events cannot be updated or deleted through normal SQL against the schema.
- Evidence conclusions are derived from matching current patch, policy, approval, and genuine passing verification records; hash mismatches are reported. Error responses and persisted verifier errors no longer expose raw submitted values or external exception text.
- Job listings are limited to 100 records per page.

See `backend/BACKEND_SECURITY_AUDIT.md` for confirmed findings separated from unconfirmed or theoretical risks.

## Verification evidence

From the project root, with the isolated local Python 3.12 environment:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/sentinel-x-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short
```

**Actual result:** 28 passed, 0 failed, 0 skipped, 1 warning, in 3.37 seconds. The warning is a third-party `StarletteDeprecationWarning` from `fastapi.testclient` regarding `httpx`; it did not affect test outcomes. The baseline before Phase 2 was 14 passed, 0 failed, 0 skipped, 1 warning.

Local Uvicorn smoke test used `SENTINEL_DB_PATH=/tmp/sentinel-x-phase2-smoke.db`, a synthetic 32+ character local token, and port 8766. Observed: `/health` returned the expected JSON and HTTP 200; `/docs` returned 200; anonymous `/api/jobs` returned 401; authenticated `/api/jobs` returned 200. The smoke server was shut down afterward. The full reproducible startup command is in `backend/README.md`.

## Current public API contracts and breaking changes

The route list is unchanged: `POST /api/findings`; `GET /api/jobs`; `GET /api/jobs/{job_id}`; `GET /api/jobs/{job_id}/patch`; `POST /api/jobs/{job_id}/approval`; `POST /api/jobs/{job_id}/verify`; `GET /api/jobs/{job_id}/evidence`; `GET /api/jobs/{job_id}/events`; plus public `GET /health` and `/docs`. Approval still requires the exact `sha256:` patch hash, and verification still requires a current approved patch. Detailed request and response shapes appear in `backend/INTEGRATION_READINESS.md` and `/docs`.

**Breaking changes:** every `/api/` call now requires `X-Operator-Token`; error responses include stable `code` values and sanitized validation details; request schemas and unified-diff syntax are stricter; POST bodies over 16 KiB default to HTTP 413; `GET /api/jobs` defaults to 100 rows and accepts `limit` (1–100) and `offset` (0+). The approval response adds `attempt`. Existing SQLite databases are migrated in place to add the approval attempt field, and a migration test passed.

## Agent and verifier integration requirements

The planner must be a reviewed public callable under `agent.*` returning the validated proposal fields. It receives only bounded authorized source context and sanitized retry feedback. Malformed output or unavailable integration transitions to `EXECUTION_ERROR`.

The verifier must be a reviewed public callable under `verification.*`, independently enforce the target and patch policy, validate the backend approval callback before applying the exact stored patch, execute required tests in an isolated environment, and return actual structured outcomes. The backend does not invent Developer 3's field names; it needs the real request/result types and status mapping before a concrete adapter can be finalized. See `backend/INTEGRATION_READINESS.md` for the exact information requested from Developers 3 and 4.

## Remaining security limits and blockers

The shared demo token is not a production identity system. SQLite files and events are not cryptographically tamper-evident, and a database owner can bypass local triggers. Thread timeouts cannot cancel a verifier that continues doing external work. Startup recovery assumes a single backend worker. The frontend must provide the token at runtime without embedding it in a public bundle. The actual agent, verifier, authorized source checkout, and Docker regression suite were unavailable locally, so no live inference or Docker verification was exercised.

**Recommended next milestone:** obtain the Developer 3 and Developer 4 contracts and the authorized demo checkout, map them into the two backend adapters, then run one real approved patch and one failing/revised patch through Docker, inspecting the stored evidence and restart behavior. Before network deployment, replace the shared token with individual authentication and isolate verifier execution in a cancellable process or worker.

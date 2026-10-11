# SENTINEL-X backend (current)

For current individual session authentication, owned project upload, and exact startup commands, see [../RUN_PROJECT.md](../RUN_PROJECT.md). The single-operator token instructions below document the preserved historical demo interface and are no longer the browser login path.

# SENTINEL-X backend

FastAPI orchestration for the authorized `bola-demo-v1` demo target. The backend stores jobs, proposals, approvals, verification results, events, and evidence in SQLite. It never executes planner-supplied commands. A patch is verified only after deterministic policy validation and approval of its exact SHA-256 hash.

## Run locally

From the project root, using Python 3.12:

```bash
python3.12 -m venv /tmp/sentinel-x-venv
/tmp/sentinel-x-venv/bin/python -m pip install -r backend/requirements.lock
export SENTINEL_ENV="demo"
export SENTINEL_DB_PATH="$PWD/backend/sentinel.db"
export SENTINEL_SOURCE_ROOT="$PWD/verification/lab"
export SENTINEL_PROTECTED_TESTS_ROOT="$PWD/verification/protected_tests"
export SENTINEL_FRONTEND_ORIGIN="http://localhost:5173"
export SENTINEL_OPERATOR_NAME="local-operator"
read -rsp 'Local operator token (32+ ASCII characters): ' SENTINEL_OPERATOR_TOKEN
echo
export SENTINEL_OPERATOR_TOKEN
export SENTINEL_AGENT_CALLABLE="agent.planner:propose_patch"
export SENTINEL_VERIFIER_CALLABLE="verification.adapter:verify_backend_patch"
export SENTINEL_PLANNER_TIMEOUT_SECONDS="60"
export SENTINEL_VERIFIER_TIMEOUT_SECONDS="300"
export SENTINEL_LEASE_SECONDS="30"
export SENTINEL_MAX_REQUEST_BYTES="16384"
/tmp/sentinel-x-venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The environment in which this backend was developed has a bundled Python 3.12 binary at `<local-path>`; use it in place of `python3.12` if needed. SQLite tables are initialized automatically when the app starts. The database defaults to `backend/sentinel.db`. Do not commit this database or the operator token. `backend/config.example.env` lists the available environment variables without a credential. Generate a random token (for example, with `openssl rand -hex 32`) and set it privately; a short or missing token does not open the API.

Open `http://127.0.0.1:8000/docs` for Swagger UI. `GET /health` returns `{"status":"ok","service":"sentinel-x-backend"}`. CORS allows only `SENTINEL_FRONTEND_ORIGIN`, defaulting to `http://localhost:5173`.

The real Docker verifier is integrated through sibling `verification/`. The planner remains unavailable in this checkout; configure a reviewed `agent.*` callable when it is supplied. If an adapter cannot run, a job transitions to `EXECUTION_ERROR`; there is no production mock. The source checkout must contain `app/access.py` under `SENTINEL_SOURCE_ROOT`. Only that file is read for planner context, with a 16 KiB limit. The bounded `verification/lab` target and configured protected test tree are hashed into each job's revision binding.

## API flow

Create a finding:

```bash
curl -X POST http://127.0.0.1:8000/api/findings \
  -H 'Content-Type: application/json' \
  -H "X-Operator-Token: $SENTINEL_OPERATOR_TOKEN" \
  -d '{"target_app_id":"bola-demo-v1","finding":{"id":"BOLA-001","type":"BROKEN_OBJECT_LEVEL_AUTHORIZATION","severity":"HIGH","file_path":"app/access.py","description":"A user can access another user’s private document."}}'
```

Response (HTTP 202): `{"job_id":"job-<uuid>","status":"FINDING_RECEIVED"}`. Planning runs in a FastAPI in-process background task. Poll `GET /api/jobs/{job_id}` for `AWAITING_APPROVAL` or an error state, then read `GET /api/jobs/{job_id}/patch` to inspect the exact proposal and its `patch_hash`.

Approve only the reviewed hash:

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/JOB_ID/approval \
  -H 'Content-Type: application/json' \
  -H "X-Operator-Token: $SENTINEL_OPERATOR_TOKEN" \
  -d '{"patch_hash":"sha256:REPLACE_WITH_64_HEX_DIGITS","decision":"APPROVE"}'
```

For local single-operator mode, `X-Operator-Token` is required for every `/api/` request, including findings, job reads, approval, and verification. The backend takes `approved_by` from `SENTINEL_OPERATOR_NAME`; a client cannot supply it. Set a long random token privately. This is not enterprise user authentication. An approval moves the job to `VERIFYING` but does not run tests automatically. Start the trusted verifier with:

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/JOB_ID/verify \
  -H "X-Operator-Token: $SENTINEL_OPERATOR_TOKEN"
```

The response includes `job_id`, `patch_hash`, workflow `status`, test counts, failed test names, duration, and any trusted verifier execution error. A real passing result returns `status: VERIFIED`. A failed test run returns `status: VERIFICATION_FAILED`; the backend immediately asks the planner for a revised patch when a revision remains. Retrieve and approve the new hash before the next `POST /verify`. After two revisions (three total proposals), another failed run moves the job to `RETRY_EXHAUSTED`.

Other endpoints: `GET /api/jobs` (default 100 rows; `limit` 1–100 and `offset` 0+), `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/patch`, `GET /api/jobs/{job_id}/evidence`, and `GET /api/jobs/{job_id}/events`. Evidence includes the finding, all patch attempts and policy decisions, all approvals, verification runs, failure history, conclusion, and limitations. The conclusion is `VERIFIED` only with a current source revision, matching approval and persisted run attestation, complete nonempty test collection, matching suite identity, and zero failures.

Invalid targets and finding paths return HTTP 422; malformed payloads also return 422 with field locations. Bodies over the configured limit return 413. Missing jobs return 404. Illegal transitions, stale patch hashes, repeated approvals or verification, and missing active approval return 409. A missing or incorrect token returns 401; an unconfigured server token returns 503 when a token is supplied. All errors use `{"detail":"safe message","code":"CODE"}`; validation errors also include sanitized `errors`. API responses use `Cache-Control: no-store`.

## Integration contracts

Configure `SENTINEL_AGENT_CALLABLE=agent.module:function` with a reviewed module under `agent.*`. The callable is imported from trusted server configuration and called as:

```python
propose_patch(finding: dict, source_context: dict[str, str], attempt: int,
              feedback: dict | None = None) -> AgentProposal | dict
```

`source_context` contains at most the authorized `app/access.py` bytes decoded as UTF-8. `attempt` is 0 for the initial proposal and 1 or 2 for revisions. Feedback includes only test totals, failed count, and bounded failed test identifiers. Return `root_cause`, `explanation`, `patch_format="unified_diff"`, `patch_text`, and `files_changed=["app/access.py"]`. The backend computes `patch_hash` from the exact UTF-8 patch bytes. The planner cannot set approval or verification state.

Configure `SENTINEL_VERIFIER_CALLABLE=verification.module:function` with a reviewed module under `verification.*`. The callable is imported from trusted server configuration and called as:

```python
verify_patch(request: VerificationRequest,
             approval_verifier: Callable[[str, str, str, str], bool]) -> VerificationResult | dict
```

`request` contains `job_id`, `target_app_id`, `patch_id`, exact stored `patch_text`, `patch_hash`, `approval_id`, `attempt`, `source_revision`, `verification_profile`, and `run_id`. The verifier **must call** `approval_verifier(job_id, patch_id, patch_hash, approval_id)` before applying the patch and reject a false result. It should independently enforce the same target/path/file-operation restrictions, apply only in an isolated authorized checkout, run required regression tests, and report `status` as `PASSED`, `FAILED`, or `EXECUTION_ERROR`; `tests_total`, `tests_passed`, `tests_failed`, `failed_tests`, `duration_ms`, and `execution_error` are part of the result. A passing result also requires `test_suite_id`, `tests_collected`, `collection_complete=true`, `execution_completed=true`, and exact echoes of `run_id`, `patch_hash`, `source_revision`, and `verification_profile`. Missing or mismatched evidence fails closed. The backend validates counts and refuses to mark zero-test runs as verified. The backend checks the stored hash and active approval before invoking the verifier. Coordinate the unified-diff path rules in `backend/policy.py` with the verification runner. The integrated Developer 3 callable is `verification.adapter:verify_backend_patch`. It checks the approval, exact source and protected-suite revision, and run binding before and after Docker execution.

The backend uses no Redis, Celery, shell command execution, or implicit demo mocks. Tests inject fake adapters only inside `backend/tests`.

## Tests

```bash
/tmp/sentinel-x-venv/bin/python -m pytest backend/tests -q
```

The suite covers ingestion, authorization, request limits, target and path rejection, strict diff parsing, state transitions, hash and attempt binding, concurrent approval and verification, rollback, restart recovery, evidence integrity, retry exhaustion, and redacted integration failures. The Phase 4 suite includes genuine Docker integration tests for a correct and an incomplete patch. The real agent remains unavailable; those tests inject a fixture planner.

## Limits

- Execution is in-process. FastAPI background planning is not a durable worker queue. Configured timeouts move stalled jobs to `EXECUTION_ERROR`, but a timed-out verifier thread may continue running briefly. Startup recovery marks interrupted planning and expired or legacy unleased verification runs `EXECUTION_ERROR`, while preserving active leases; a process crash during an external verifier call may leave external side effects that the backend cannot undo.
- An approved job waits in `VERIFYING` for an explicit `POST /verify`; it remains pending until that call is made.
- SQLite is suitable for this single-process hackathon MVP, not a distributed deployment. WAL, transactions, compare-and-set state transitions and leases protect routine concurrency on one host; multiple hosts need a stronger execution architecture.
- The local operator token is shared by the one operator and cannot establish individual identity. Production configuration intentionally fails startup until identity and verifier isolation are implemented. Keep it out of bundled frontend code and use TLS and real authentication before network deployment.
- The backend records verifier-reported evidence from actual Docker tests in Phase 4. Production deployment still requires isolated worker lifecycle controls and an individual identity provider.

See `backend/BACKEND_SECURITY_AUDIT.md` for confirmed findings and remaining risks, `backend/INTEGRATION_READINESS.md` for team contracts, and `backend/BACKEND_PHASE2_REPORT.md` for Phase 2 results.

## Phase 3 controls and validation

Run `PYTHON_BIN=/tmp/sentinel-x-venv/bin/python backend/security_check.sh` from the project root for AST parse, dependency consistency, tests, and an optional vulnerability audit when `pip-audit` is installed. `backend/requirements.lock` pins the local Python environment, and `backend/sbom.spdx.json` inventories installed packages; neither provides hashes or vulnerability assurance. See `backend/THREAT_MODEL.md`, `backend/SECURITY_INVARIANTS.md`, `backend/SECURITY_ARCHITECTURE.md`, `backend/PRODUCTION_READINESS.md`, and `backend/PHASE3_SECURITY_REPORT.md` for design, operational blockers and actual validation results.

## Phase 4 backend–verifier integration

Build the existing verifier image with `docker build -t sentinel-verification-lab:latest -f verification/Dockerfile verification/`. Set `SENTINEL_SOURCE_ROOT` to `verification/lab`, `SENTINEL_PROTECTED_TESTS_ROOT` to `verification/protected_tests`, and `SENTINEL_VERIFIER_CALLABLE=verification.adapter:verify_backend_patch`. The adapter requires an exact Phase 3 run ID, patch hash, source revision, attempt and verification profile. The protected suite contributes to the source revision. Run `PYTHONDONTWRITEBYTECODE=1 /tmp/sentinel-x-venv/bin/python -m pytest backend/tests verification/tests -q -p no:cacheprovider --tb=short` for the complete backend and verifier regression suite. See `backend/PHASE4_INTEGRATION_REPORT.md` for actual results and remaining limits.

# SENTINEL-X local audit — 11 October 2026

**Docker follow-up:** Docker is now installed and its Linux daemon is operational. The verifier image was built and all ten previously Docker-blocked tests pass. Latest full suite: **176 passed, 2 failed**, 32 subtests passed. The two remaining failures are Windows newline/symlink issues. See `DOCKER_AUDIT_REPORT.md`; the initial audit below remains a historical record.

## Result

The supplied folder contains an implemented backend, constrained AI patch planner, reflection module, and Docker verification code. The backend starts and serves real HTTP requests on this Windows machine. The complete remediation product cannot currently run here: the frontend is absent, Ollama has no installed models, and Docker is unavailable. No new patch was generated, approved, or verified during this audit.

This is fresh execution evidence, separate from the historical Phase 5/6 reports. No application source, protected tests, security policy, or original database was edited. Added only audit/startup scripts, this report, a local virtual environment, and audit artifacts.

## Actual execution

- Python 3.12.14 from the bundled runtime; project-local `.venv` created.
- Installed the README dependencies, including pinned direct backend dependencies and Neatlogs 1.4.26. `pip check`: no broken requirements. Transitive Neatlogs dependencies resolved at installation time; this is not a fully locked historical environment.
- Full original suite: **166 passed, 12 failed, 32 subtests passed**, 9 warnings, 13.25 seconds. All 178 tests ran; Docker tests were not silently skipped. See `local-audit/regression.log` and `regression.xml`.
- Started actual Uvicorn/FastAPI subprocess on localhost, with configured real planner/verifier and a fresh database. Nine HTTP status checks passed: health, readiness, missing/wrong-token rejection, authenticated job list, invalid-input rejection, finding creation, evidence and event retrieval.
- A real finding returned HTTP 202 and transitioned `FINDING_RECEIVED → PLANNING → EXECUTION_ERROR`. No proposal existed; evidence remained `NOT_VERIFIED`. No approval or verification request was issued. See `local-audit/http-results.json` and `backend-http.log`.
- Supplied inference smoke script: `GenerationError`, `Patch generation failed (ProviderError)`, 0.08 seconds. Ollama `/api/tags` returned HTTP 200 with an empty model list. No mock inference was substituted.
- Neatlogs local Doctor: **pass**, 4 spans, successful flush. Hosted export was not tested; `NEATLOGS_API_KEY` is unset. Doctor tests SDK capture, not the application's complete trace delivery.
- Supplied SQLite database opened read-only: integrity `ok`, zero jobs, proposals, approvals, verification runs, and workflow events. Historical successful-run evidence is not present in that database.
- Temporary HTTP audit servers were stopped after testing. Ollama was left running as found.

## Why 12 tests failed

| Count | Cause | Interpretation |
| --- | --- | --- |
| 10 | Real Docker integration tests receive `EXECUTION_ERROR` because Docker is missing | Verification cannot execute on this machine; this does not establish that the implementation fails when Docker is properly configured |
| 1 | `backend/tests/test_api.py::test_health_ingestion_listing_and_docs` expects LF, while its Windows-created source fixture is CRLF | Cross-platform newline assumption; the backend reads raw bytes rather than normalizing them |
| 1 | `backend/tests/test_phase3_security.py::test_manifest_revision_and_symlink_rejected` raises WinError 1314 creating a symlink | Windows privilege limitation; the rejection logic was not reached by this test |

Warnings concern unregistered `docker` markers and deprecated TestClient use of httpx. They were not the cause of failures.

## Implemented versus verified here

| Component | What exists | Fresh local result |
| --- | --- | --- |
| Backend | Finding intake, SQLite jobs, policy, state machine, hash-bound approval, source binding, evidence and events | Starts; core HTTP checks pass; relevant logic covered by passing tests |
| Agent A | Ollama adapter, authorized context, structured guard parsing, AST checks, deterministic diff generation | Mocked generation tests pass; real inference fails because no model is installed |
| Agent B | Sanitized reflection and bounded revision guidance | Unit/contract tests pass; real-model correction loop unverified |
| Approval | Exact-hash decision binding; revised patches need fresh approval | Tests exercise approval logic; no new human approval performed |
| Verifier | Restricted Docker command, protected test suite, deterministic evidence evaluator | Policy/evaluator tests pass; ten Docker integration cases blocked locally |
| Frontend | No frontend folder, package.json, React source, or frontend ZIP in the supplied workspace | Cannot build or browser-test |
| Observability | Neatlogs adapter and local SDK | Doctor passes; actual observer disables itself without a key; hosted export unverified |
| Recorded demo | Historical reports describe successful execution | Database is empty; saved proposal/evidence files referenced under the former Linux `/tmp` are absent from this copy |

## Findings from source inspection

1. **AI scope is deliberately narrow.** `agent/generator.py` requests a two-line ownership guard. `agent/edits.py` requires a comparison between `doc["owner_id"]` and `requesting_user_id`, followed by `PermissionError`, and inserts it before a specific return anchor. This is a constrained BOLA demonstration, not an arbitrary repository/CVE remediation engine.
2. **Readiness overstates dependency availability.** `/ready` returns 200 when token, callable configuration, and database are present. It does not probe Ollama/model availability, Docker, its image, or the host patch utility. The audit observed `ready` while inference and Docker verification were unavailable.
3. **Windows setup needs work.** README startup commands are Linux commands. The verifier invokes host `patch`, which is not on PATH here (Git's `usr/bin/patch.exe` does exist). Docker must also be configured, the verifier image built, and Windows bind mounts exercised. The smoke script writes successful output to hardcoded `/tmp/sentinel-phase5-ai-proposal.json`; use a portable, explicitly selected output directory before successful Windows inference.
4. **Newlines matter beyond tests.** `build_guard_diff` looks for exact LF source anchors. CRLF checkouts can fail this match. Any solution must preserve the authoritative source revision and exact patch integrity rather than silently changing approval bindings.
5. **Trace correlation is incomplete.** Planner metadata supplies attempt/model but no job ID. Observer metadata only accepts attempts starting at 1, so initial attempt 0 is omitted. Without an API key, this observer performs no SDK capture; the standalone local Doctor passing does not mean the agent emits local application traces.
6. **Some documents are stale.** `backend/PRODUCTION_READINESS.md` says the real planner is absent, but `agent/planner.py` is present and configured. Read old reports as historical snapshots. Production mode is intentionally rejected by configuration; demo shared-token identity and in-process orchestration remain limitations.

## Remaining work, in practical order

1. Supply Developer 2's actual frontend source and integrate it with `docs/PHASE6_API_CONTRACT.md` (token header, response fields, asynchronous planning/polling, long verification calls).
2. Install or otherwise provide a working Docker CLI/daemon, host patch utility, and `sentinel-verification-lab:latest` image. Prefer the previously tested Linux setup or validate Windows explicitly.
3. Download `qwen2.5-coder:7b` into Ollama, then rerun real inference. No large model download or Docker installation was performed during this audit.
4. Address newline assumptions, symlink-test setup, and the portable smoke-artifact path. Re-run failing cases after their blockers are resolved.
5. Run one fresh browser-driven finding → proposal → human approval → Docker verification → evidence workflow.
6. Demonstrate a real-model failure/reflection/revision cycle if that capability is part of the pitch.
7. Recover or regenerate genuine saved proposal/evidence for a clearly labeled recorded demo. Do not recreate the historical result from prose.
8. Configure hosted Neatlogs if required, verify actual agent trace delivery, and complete submission materials. Partner requirements are unverified in this audit.

## Re-run locally

From the project directory in PowerShell:

```powershell
& .\scripts\start_local_backend.ps1
```

This starts the actual backend on port 8000 with a separate `local-audit/local-server.db`, preserving `backend/sentinel.db`. It creates a token in the current process environment if one is not already set, without printing it. Swagger is at `http://127.0.0.1:8000/docs`; authenticated `/api/` calls require `X-Operator-Token`. The missing-model/Docker blockers still apply.

To repeat the HTTP audit (it starts and stops its own server):

```powershell
$env:PYTHONPATH = '.'
& .\.venv\Scripts\python.exe .\scripts\local_audit.py
```

To repeat the original suite:

```powershell
$env:SENTINEL_DB_PATH = 'local-audit/test-import.db'
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -m pytest agent/tests backend/tests verification/tests -q -p no:cacheprovider --tb=short
```

The original 178-passing Linux baseline has not been reproduced here. The project has a substantial implemented core, but this supplied copy is not yet a complete locally runnable application.

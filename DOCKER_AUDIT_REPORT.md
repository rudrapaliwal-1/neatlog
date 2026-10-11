# Docker verification follow-up — 11 October 2026

Docker setup and actual fixture verification now work on this Windows laptop. All ten integration tests that failed previously because Docker was unavailable now pass.

## Environment and changes

- Docker Desktop 4.94.0, Docker client/server 29.8.2, `desktop-linux` context, Linux/amd64 engine.
- Docker CLI found at `C:/Users/Dell/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe`.
- GNU patch 2.7.6 from `C:/Program Files/Git/usr/bin/patch.exe`.
- Built the original `verification/Dockerfile` as `sentinel-verification-lab:latest`.
- Image ID: `sha256:ce36b14f3d66c3239b1bdb927b31cf328aad2e847f1fcd811dc4ab65b363335d`; configured container user `sandboxuser`.
- Updated `scripts/start_local_backend.ps1` to add installed Docker/Git tool directories to its process PATH. No global PATH, Dockerfile, verifier policy, or protected tests were changed.
- Added `scripts/docker_fixture_audit.py` to capture reproducible real Docker results for trusted, labeled fixtures.

## Fresh execution evidence

| Fixture | Actual Docker verdict | Tests passed | Tests failed |
| --- | --- | --- | --- |
| `correct_patch.diff` | `VERIFIED` | 8 | 0 |
| `incomplete_patch.diff` | `VERIFICATION_FAILED` | 5 | 3 |

Both runs collected eight tests and reported `collection_complete=true`, `execution_completed=true`, with no execution error. Evidence is in `local-audit/docker-fixture-results.json` and `docker-fixture.log`. The verifier used its actual restricted container command, including no network, non-root execution, resource limits, read-only root filesystem, and protected tests mounted read-only.

These patches are test fixtures, not AI-generated patches. The standalone audit uses an explicitly labeled automated fixture approval callback. Automated approvals in the regression suite likewise exercise test behavior; they are not claims of new human authorization for an AI proposal.

Full original suite with Docker/GNU patch on PATH: **176 passed, 2 failed, 32 subtests passed**, 9 warnings, 62.02 seconds. Evidence: `local-audit/docker-regression.log` and `docker-regression.xml`.

Passing integration coverage includes backend approval → Docker → persisted evidence, correct/incomplete verdict translation, concurrent isolated runs, repeated deterministic results, and the fixture-driven failure/revision workflow. That revision test confirms a changed patch hash, rejection of verification under old approval, fresh approval requirement, and subsequent eight-test success.

## Two remaining failures

1. `backend/tests/test_api.py::test_health_ingestion_listing_and_docs`: Windows-created source fixture has CRLF while the assertion expects LF.
2. `backend/tests/test_phase3_security.py::test_manifest_revision_and_symlink_rejected`: Windows refuses symlink creation with WinError 1314 before the rejection logic can be exercised.

These are the same non-Docker failures observed initially. They were not bypassed or counted as passing. Existing warnings concern unregistered Docker markers and TestClient's deprecated httpx integration.

## What remains

The frontend is still pending delivery from the team. This work establishes real Docker verification of prepared patches and fixture-driven backend revision orchestration. It does not establish a new real-model inference or live AI self-correction run. Ollama's missing-model result from the earlier audit remains the latest check of that component.

Restart an already-running backend with `scripts/start_local_backend.ps1` so it inherits the updated tool PATH. The verifier image stays installed for future runs.

To repeat the standalone fixture audit from the project directory:

```powershell
$env:PATH = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:ProgramFiles\Git\usr\bin;" + $env:PATH
$env:PYTHONPATH = '.'
& .\.venv\Scripts\python.exe scripts/docker_fixture_audit.py
```

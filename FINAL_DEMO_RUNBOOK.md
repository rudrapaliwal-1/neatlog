# Phase 8 local demonstration runbook

Run from this project root. Use a fresh local SQLite file for each demonstration and preserve `local-audit/phase7-browser.db` and the Phase 8 proof files. Do not publish the source or place `.env` credentials in frontend variables.

## Prerequisites

Python 3.12, the dependencies in `backend/requirements.txt`, Docker with current-user daemon access, the trusted verifier image, Ollama with `qwen2.5-coder:7b`, Node.js and frontend dependencies are required. This host has `/tmp/sentinel-x-py/bin/python` and `frontend/node_modules` ready. To rebuild the image from the trusted verifier source:

```bash
docker build -t sentinel-verification-lab:latest -f verification/Dockerfile verification/
```

Check without starting duplicate services:

```bash
ss -ltnp | rg ':8001|:5173|:11434'
ollama list
docker info
```

## Set local backend configuration

```bash
export PYTHONPATH=.
export SENTINEL_DB_PATH=local-audit/demo-live.db
export SENTINEL_PROJECT_ROOT=local-audit/demo-live-projects
export SENTINEL_SOURCE_ROOT=verification/lab
export SENTINEL_PROTECTED_TESTS_ROOT=verification/protected_tests
export SENTINEL_FRONTEND_ORIGIN=http://127.0.0.1:5173
export SENTINEL_AGENT_CALLABLE=agent.planner:propose_patch
export SENTINEL_VERIFIER_CALLABLE=verification.adapter:verify_backend_patch
export SENTINEL_PLANNER_TIMEOUT_SECONDS=300
export SENTINEL_INFERENCE_TIMEOUT=280
export SENTINEL_MAX_TOKENS=350
export SENTINEL_PROVIDER_RETRIES=0
mkdir -p "$SENTINEL_PROJECT_ROOT"
/tmp/sentinel-x-py/bin/python scripts/startup_check.py --backend-port 8001 --frontend-port 5173
```

A preflight status of `not_ready` includes actions for missing model, Docker, image, patch utility, callables or paths. It may say the backend/frontend ports are `free` before launch. Resolve critical checks before starting. If a port is occupied, inspect it; do not terminate unrelated services. Choose free alternate ports and update both origin variables consistently when necessary.

## Start services

In one terminal, only if Ollama is not already serving:

```bash
ollama serve
```

In a separate terminal, from the project root:

```bash
/tmp/sentinel-x-py/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

In another terminal:

```bash
cd frontend
PATH=<local-path> \
VITE_API_BASE_URL=http://127.0.0.1:8001 ./node_modules/.bin/vite --host 127.0.0.1 --port 5173
```

Confirm `curl http://127.0.0.1:8001/health` reports alive and `curl http://127.0.0.1:8001/ready` reports ready. Open `http://127.0.0.1:5173`.

## Prepare controlled ZIP

The committed trusted lab source contains an intentional BOLA defect. Create a ZIP for the authorized demonstration:

```bash
python3 - <<'PY'
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
out = Path('local-audit/demo-upload.zip')
out.parent.mkdir(exist_ok=True)
with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('requirements.txt', 'fastapi==0.143.0\n')
    for name in ('__init__.py', 'access.py', 'sample_data.py'):
        archive.write(Path('verification/lab/app') / name, 'app/' + name)
print(out.resolve())
PY
```

## Browser walkthrough

1. Register a local test account and refresh once to verify session restoration.
2. Upload the ZIP under **Projects**. Confirm `SUPPORTED_BOLA_CONTRACT`, Python/FastAPI, source revision and source files.
3. Select the BOLA finding. Wait for genuine Qwen generation; CPU inference can take several minutes. If it times out or policy rejects the proposal, report that result and rerun only after diagnosing it.
4. Review the diff and SHA-256 hash. Click **Approve patch** manually. Click **Request verification**. Inspect the eight protected test results and the actual verdict.
5. Open **Evidence reports**, query the job ID, and inspect patch hash, source revision, run ID, approval binding and attestation. Refresh and query again to prove persistence.
6. Log out, register a second test account, verify the project list is empty, and query the first account's job/evidence. Access must be denied as `job not found`.

The baseline/fixture proof scripts may be run independently. They are clearly labeled and must not be described as a Qwen run:

```bash
PYTHONPATH=. /tmp/sentinel-x-py/bin/python scripts/baseline_docker_proof.py
PYTHONPATH=. /tmp/sentinel-x-py/bin/python scripts/phase8_docker_proof.py
PYTHONPATH=. /tmp/sentinel-x-py/bin/python -m pytest agent/tests/test_fixture_integration.py -q
```

## Regression and evidence location

```bash
PYTHONPATH=. /tmp/sentinel-x-py/bin/python -m pytest agent/tests backend/tests verification/tests -q
cd frontend
PATH=<local-path> ./node_modules/.bin/tsc --noEmit
PATH=<local-path> ./node_modules/.bin/vite build
```

`local-audit/phase8-vulnerable-baseline.json` and `local-audit/phase8-bc-proof.jsonl` hold fresh Docker summaries. The browser evidence lives in the configured demo SQLite database. Keep these local files private; the browser's **Evidence reports** page is the presentation surface.

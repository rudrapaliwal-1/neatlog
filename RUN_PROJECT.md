# Run SENTINEL-X locally

Use the project root containing `backend/`, `agent/`, `verification/` and `frontend/`. Python 3.12, Docker, Ollama, Node.js and npm are required. SQLite is created automatically at backend startup.

## 1. Install dependencies

```bash
python3.12 -m venv /tmp/sentinel-x-py
/tmp/sentinel-x-py/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

On this host, the bundled Python executable is `<local-path>`. The bundled Node binary is `<local-path>`. A project `frontend/node_modules` is already present; its `vite` and `tsc` commands were executed successfully. A fresh `npm ci` install was not retested on this host because `npm` is not on its PATH.

## 2. Check model and start sandbox

```bash
ollama list
# In a separate terminal, only if Ollama is not already serving:
ollama serve
# qwen2.5-coder:7b is already installed on the tested host; do not pull it again.
docker info
docker build -t sentinel-verification-lab:latest -f verification/Dockerfile verification/
```

The Docker daemon and image must exist. Uploaded code is never run on the host. The verifier uses the trusted image and protected tests only.

## 3. Start backend

From the project root:

```bash
export PYTHONPATH=.
export SENTINEL_DB_PATH=backend/sentinel.db
export SENTINEL_PROJECT_ROOT=backend/project_data
export SENTINEL_SOURCE_ROOT=verification/lab
export SENTINEL_PROTECTED_TESTS_ROOT=verification/protected_tests
export SENTINEL_FRONTEND_ORIGIN=http://127.0.0.1:5173
export SENTINEL_AGENT_CALLABLE=agent.planner:propose_patch
export SENTINEL_VERIFIER_CALLABLE=verification.adapter:verify_backend_patch
export SENTINEL_PLANNER_TIMEOUT_SECONDS=300
export SENTINEL_INFERENCE_TIMEOUT=280
export SENTINEL_MAX_TOKENS=350
export SENTINEL_PROVIDER_RETRIES=0
/tmp/sentinel-x-py/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

The normal browser workflow needs no operator token. An optional `SENTINEL_OPERATOR_TOKEN` can preserve the old internal demo API, but it cannot access user-owned projects. Never put the token or `NEATLOGS_API_KEY` in frontend code. `/health` and `/ready` report backend availability; `/ready` does not prove the model or Docker will succeed.

## 4. Start frontend

With a standard Node/npm install:

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1 --port 5173
```

On the tested host with preinstalled `frontend/node_modules`:

```bash
cd frontend
PATH=<local-path> \
  VITE_API_BASE_URL=http://127.0.0.1:8001 ./node_modules/.bin/vite --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

## 5. Create the first user and run the workflow

In the browser, choose **Register**, enter an email and a password of at least 12 characters, then open **New Project → Upload Repository**. Enter a name and upload a ZIP containing the supported contract. The repository must declare FastAPI in `requirements.txt` or `pyproject.toml`, provide `app/access.py` with `get_document` and the expected return anchor, and provide `app/sample_data.py` for the trusted document-access tests. The demo ZIP can be built from `verification/lab/app` using [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).

Select the project, confirm the BOLA finding, and start AI remediation. The job page polls while Qwen runs. Review the diff and patch hash, explicitly approve it, click **Request verification**, and inspect the test results and **Evidence reports**. On failure, any new revision needs a fresh approval.

To run tests:

```bash
PYTHONPATH=. /tmp/sentinel-x-py/bin/python -m pytest agent/tests backend/tests verification/tests -q
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vite build
```

## Phase 8 preflight and readiness

Before starting new processes, export the variables from step 3 and run:

```bash
PYTHONPATH=. /tmp/sentinel-x-py/bin/python scripts/startup_check.py --backend-port 8001 --frontend-port 5173
```

The preflight is read-only with respect to services: it does not start or stop processes. It reports occupied ports and whether an HTTP service answers on them. If a port is occupied but unreachable, inspect the owner with `ss -ltnp` and choose another port; do not kill an unrelated process. If the backend is already reachable, use it instead of starting a duplicate. For a different backend port, set `VITE_API_BASE_URL` to that exact URL before launching Vite, and set `SENTINEL_FRONTEND_ORIGIN` to the exact frontend origin before launching the backend.

`GET /health` means FastAPI is alive. `GET /ready` performs bounded local checks of SQLite, configured trusted callables, application paths, Ollama, the configured Qwen model, Docker daemon, `sentinel-verification-lab:latest`, and the host `patch` utility. It returns HTTP 503 and an actionable `checks` object for missing critical dependencies. Neatlogs is listed separately as optional and unverified; it cannot affect the verifier verdict. A ready response does not assert hosted telemetry delivery or that a future model response will pass policy.

A missing Ollama service calls for `ollama serve`; a missing model calls for installing the configured `SENTINEL_MODEL` (default `qwen2.5-coder:7b`); a missing Docker image calls for the Docker build command in step 2. Recheck `/ready` after resolving a dependency. Do not place API keys in shell transcripts or frontend variables.

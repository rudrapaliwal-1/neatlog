# SENTINEL-X clean submission

This copy contains the application source, tests, supported verifier lab and protected tests, dependency manifests and locks, configuration templates, and project documentation. It contains no live credentials or local runtime evidence. The root `.env.example` has an empty `NEATLOGS_API_KEY` field; set secrets only in a private `.env` or secret store outside any submitted archive.

## Reproduce the supported demo

1. Use Python 3.12, Node.js, npm, Docker, and Ollama with the configured `qwen2.5-coder:7b` model. Install backend dependencies with `python3.12 -m venv .venv` and `.venv/bin/python -m pip install -r backend/requirements.lock`; install frontend dependencies with `cd frontend && npm ci`.
2. From this directory, run `docker build -t sentinel-verification-lab:latest -f verification/Dockerfile verification/`. Review `RUN_PROJECT.md` for the backend environment variables and startup commands. Set `PYTHONPATH=.`. Build the demo upload ZIP from `verification/lab/app` as described in `DEMO_RUNBOOK.md`.
3. Start Ollama, then the backend and frontend as described in `RUN_PROJECT.md`. Register a fresh demo user and follow the project upload, finding, remediation, exact-hash approval, and Docker verification workflow. Neatlogs is optional and off by default; `NEATLOGS_DEMO_GUIDE.md` describes its opt-in modes.
4. Run backend tests with `PYTHONPATH=. .venv/bin/python -m pytest agent/tests backend/tests verification/tests -q`. From `frontend/`, run `npm run build`.

No uploaded repository, runtime SQLite database, generated frontend bundle, dependency directory, or private audit output is included. They are recreated by the documented workflow. SHA256SUMS lists the included files and provides an integrity check. Historical reports retain their findings but private runtime IDs, hosted trace links, and machine-specific paths have been redacted in this copy.

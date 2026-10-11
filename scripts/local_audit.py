"""Run the actual backend over HTTP with a fresh audit database and ephemeral token.

Does not approve patches, substitute inference fixtures, or execute generated code.
Stops only its own backend subprocess when finished.
"""
from pathlib import Path
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "local-audit"


def main():
    OUT.mkdir(exist_ok=True)
    token = secrets.token_urlsafe(48)
    env = os.environ.copy()
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    env.update(SENTINEL_OPERATOR_TOKEN=token,
               SENTINEL_DB_PATH=str(OUT / ("http-" + secrets.token_hex(6) + ".db")),
               SENTINEL_PROVIDER_RETRIES="0", SENTINEL_INFERENCE_TIMEOUT="15",
               SENTINEL_PLANNER_TIMEOUT_SECONDS="20", PYTHONDONTWRITEBYTECODE="1")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    result = {"utc_time": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "url": f"http://127.0.0.1:{port}",
              "checks": {}, "uses_real_planner": True, "patch_approved": False}
    original_db = ROOT / "backend" / "sentinel.db"
    if original_db.exists():
        with sqlite3.connect(original_db.as_uri() + "?mode=ro", uri=True) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            counts = {}
            for name in ("jobs", "patch_proposals", "approvals", "verification_runs", "workflow_events"):
                if name in tables:
                    counts[name] = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            result["supplied_database_counts"] = counts
            result["supplied_database_integrity"] = db.execute("PRAGMA quick_check").fetchone()[0]
            if "jobs" in tables:
                result["supplied_job_statuses"] = dict(db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status"))
    with (OUT / "backend-http.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app",
                                    "--host", "127.0.0.1", "--port", str(port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=result["url"], timeout=10, trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Backend exited; inspect backend-http.log")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Backend startup timed out")
                headers = {"X-Operator-Token": token}
                def check(name, method, path, expected, **kwargs):
                    response = client.request(method, path, **kwargs)
                    try:
                        body = response.json()
                    except ValueError:
                        body = "non-JSON response"
                    result["checks"][name] = {"http_status": response.status_code,
                                             "expected_status": expected,
                                             "passed": response.status_code == expected,
                                             "body": body}
                    return body
                check("health", "GET", "/health", 200)
                check("ready", "GET", "/ready", 200)
                check("unauthenticated_jobs", "GET", "/api/jobs", 401)
                check("wrong_token_jobs", "GET", "/api/jobs", 401,
                      headers={"X-Operator-Token": "invalid"})
                check("authenticated_jobs", "GET", "/api/jobs", 200, headers=headers)
                check("invalid_finding", "POST", "/api/findings", 422, headers=headers, json={})
                finding = {"target_app_id": "bola-demo-v1", "finding": {
                    "id": "LOCAL-AUDIT-BOLA", "type": "BROKEN_OBJECT_LEVEL_AUTHORIZATION",
                    "severity": "HIGH", "file_path": "app/access.py",
                    "description": "Document lookup returns another user's document without checking ownership."}}
                created = check("finding_intake", "POST", "/api/findings", 202,
                                headers=headers, json=finding)
                job_id = created.get("job_id")
                if job_id:
                    for _ in range(120):
                        response = client.get(f"/api/jobs/{job_id}", headers=headers)
                        job = response.json()
                        if job.get("status") not in ("FINDING_RECEIVED", "PLANNING"):
                            break
                        time.sleep(0.25)
                    result["live_job"] = job
                    check("job_evidence", "GET", f"/api/jobs/{job_id}/evidence", 200, headers=headers)
                    check("job_events", "GET", f"/api/jobs/{job_id}/events", 200, headers=headers)
                    result["patch_endpoint"] = {"http_status": client.get(
                        f"/api/jobs/{job_id}/patch", headers=headers).status_code}
            with httpx.Client(timeout=5, trust_env=False) as client:
                try:
                    response = client.get("http://127.0.0.1:11434/api/tags")
                    result["ollama"] = {"http_status": response.status_code,
                                        "models": [item["name"] for item in response.json().get("models", [])]}
                except httpx.HTTPError as error:
                    result["ollama"] = {"error_type": type(error).__name__}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    (OUT / "http-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

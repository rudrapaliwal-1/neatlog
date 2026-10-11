"""Diagnostic only: run trusted protected tests on unpatched lab source in Docker."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.manifest import TARGET_MANIFEST

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    (ROOT / "verification/.tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sentinel-baseline-", dir=ROOT / "verification/.tmp") as temporary:
        workspace = Path(temporary)
        app = workspace / "app"
        tests = workspace / "protected_tests"
        report = workspace / "report"
        shutil.copytree(ROOT / "verification/lab/app", app)
        shutil.copytree(ROOT / "verification/protected_tests", tests)
        report.mkdir()
        workspace.chmod(0o755)
        report.chmod(0o777)
        command = ["docker", "run", "--rm", "--network", "none", "--memory", "512m",
                   "--cpus", "1.0", "--pids-limit", "64", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--read-only",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                   "-e", "VERIFICATION_REPORT_PATH=/workspace/report/test_report.json",
                   "-e", "PYTHONPATH=/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1",
                   "-v", f"{app}:/workspace/verification/lab/app:ro",
                   "-v", f"{tests}:/workspace/verification/protected_tests:ro",
                   "-v", f"{report}:/workspace/report:rw",
                   "sentinel-verification-lab:latest", "pytest", "-p", "no:cacheprovider",
                   "/workspace/verification/protected_tests", "-q"]
        try:
            run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 timeout=120, check=False)
            payload = json.loads((report / "test_report.json").read_text())
            summary = payload["summary"]
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            print(json.dumps({"status": "EXECUTION_ERROR", "docker_execution": "failed",
                              "stage": type(exc).__name__, "docker_exit_code": run.returncode if "run" in locals() else None,
                              "report_exists": (report / "test_report.json").exists()}))
            return 2
        result = {"executed_at": datetime.now(timezone.utc).isoformat(),
                  "source_revision": TARGET_MANIFEST.source_revision(ROOT / "verification/lab", ROOT / "verification/protected_tests"),
                  "profile": TARGET_MANIFEST.verification_profile, "patch_hash": None,
                  "docker_exit_code": run.returncode, "summary": summary,
                  "verdict": "VULNERABILITY_DETECTED" if run.returncode == 1 and summary["failed"] > 0 else "UNEXPECTED_RESULT",
                  "evidence_id": "baseline-" + uuid4().hex, "diagnostic_only": True,
                  "backend_attestation": False}
        print(json.dumps(result, sort_keys=True))
        return 0 if result["verdict"] == "VULNERABILITY_DETECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

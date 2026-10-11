"""Preflight for the local demo; read-only and never starts or stops services."""
from __future__ import annotations

import argparse
import json
import socket
from urllib.request import urlopen

from backend.config import Settings
from backend.database import Database
from backend.readiness import probe
from backend.services.agent_adapter import ConfiguredAgentAdapter
from backend.services.verification_adapter import ConfiguredVerificationAdapter
from backend.workflow import Workflow


def port_state(host: str, port: int) -> str:
    try:
        with socket.create_connection((host, port), timeout=1):
            return "occupied"
    except OSError:
        return "free"


def reachable(url: str, marker: bytes) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200 and marker in response.read(16_384)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local SENTINEL-X dependencies and ports")
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        workflow = Workflow(Database(settings.database_path), settings,
                            ConfiguredAgentAdapter(settings), ConfiguredVerificationAdapter(settings))
        result = probe(workflow)
    except (ValueError, OSError, RuntimeError):
        print("Invalid application configuration. Check SENTINEL_* variables and local paths.")
        return 2
    print(json.dumps(result, indent=2))
    for label, port, suffix, marker in (("backend", args.backend_port, "/health", b"sentinel-x-backend"),
                                        ("frontend", args.frontend_port, "/", b"SENTINEL-X")):
        state = port_state("127.0.0.1", port)
        works = reachable(f"http://127.0.0.1:{port}{suffix}", marker) if state == "occupied" else False
        print(f"{label} port {port}: {state}; {'reachable' if works else 'not reachable'}")
        if state == "occupied" and not works:
            print(f"{label}: another process may own the port; choose another port or inspect it before starting")
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded local dependency probes; never return raw subprocess or network errors."""
from __future__ import annotations

import json
import shutil
import subprocess
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from .services.agent_adapter import ConfiguredAgentAdapter, load_callable
from .services.verification_adapter import ConfiguredVerificationAdapter


def _command(arguments: list[str]) -> bool:
    try:
        return subprocess.run(arguments, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=3, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe(workflow) -> dict:
    """Keep health checks small and independent of uploaded repository content."""
    settings = workflow.settings
    checks: dict[str, dict[str, str]] = {}

    def add(name: str, ok: bool, hint: str) -> None:
        checks[name] = {"status": "ready" if ok else "unavailable",
                        "action": "none" if ok else hint}

    try:
        with workflow.db.read() as db:
            add("database", db.execute("SELECT 1").fetchone()[0] == 1,
                "Check SENTINEL_DB_PATH and SQLite permissions")
    except Exception:
        add("database", False, "Check SENTINEL_DB_PATH and SQLite permissions")

    agent_active = isinstance(workflow.agent, ConfiguredAgentAdapter)
    verifier_active = isinstance(workflow.verifier, ConfiguredVerificationAdapter)
    try:
        agent_ok = bool(settings.agent_callable) and callable(load_callable(settings.agent_callable, "agent")) if agent_active else callable(getattr(workflow.agent, "propose_patch", None))
    except Exception:
        agent_ok = False
    try:
        verifier_ok = bool(settings.verifier_callable) and callable(load_callable(settings.verifier_callable, "verification")) if verifier_active else callable(getattr(workflow.verifier, "verify_patch", None))
    except Exception:
        verifier_ok = False
    add("agent_callable", agent_ok, "Configure SENTINEL_AGENT_CALLABLE to an installed trusted callable")
    add("verifier_callable", verifier_ok, "Configure SENTINEL_VERIFIER_CALLABLE to an installed trusted callable")
    add("configuration", bool(settings.source_root.is_dir() and settings.project_root.parent.is_dir() and
                              (not verifier_active or (settings.protected_tests_root is not None and settings.protected_tests_root.is_dir()))),
        "Check SENTINEL_SOURCE_ROOT, SENTINEL_PROJECT_ROOT and SENTINEL_PROTECTED_TESTS_ROOT")

    if agent_active:
        from os import getenv
        model = getenv("SENTINEL_MODEL", "qwen2.5-coder:7b")
        endpoint = getenv("SENTINEL_OLLAMA_URL", "http://127.0.0.1:11434")
        service_ok = model_ok = False
        parsed = urlsplit(endpoint)
        if parsed.scheme in ("http", "https") and parsed.netloc and not parsed.username and not parsed.password:
            try:
                with urlopen(Request(endpoint.rstrip("/") + "/api/tags", headers={"Accept": "application/json"}), timeout=3) as response:
                    payload = response.read(262_145)
                    service_ok = response.status == 200 and len(payload) <= 262_144
                if service_ok:
                    data = json.loads(payload)
                    model_ok = any(item.get("name") == model or item.get("model") == model
                                   for item in data.get("models", []) if isinstance(item, dict))
            except Exception:
                pass
        add("ollama", service_ok, "Start Ollama and check SENTINEL_OLLAMA_URL")
        add("model", model_ok, "Install the configured SENTINEL_MODEL in Ollama")
    if verifier_active:
        docker = shutil.which("docker")
        daemon_ok = bool(docker and _command([docker, "info", "--format", "{{.ServerVersion}}"]))
        add("docker", daemon_ok, "Start Docker and grant the current user daemon access")
        add("verifier_image", bool(daemon_ok and _command([docker, "image", "inspect", "sentinel-verification-lab:latest"])),
            "Build sentinel-verification-lab:latest from verification/Dockerfile")
        patch_tool = shutil.which("patch")
        add("patch_utility", bool(patch_tool and _command([patch_tool, "--version"])),
            "Install the system patch utility")
    return {"status": "ready" if all(value["status"] == "ready" for value in checks.values()) else "not_ready",
            "checks": checks, "optional_integrations": {"neatlogs": "configured_unverified" if __import__("os").getenv("NEATLOGS_API_KEY") else "not_configured"}}

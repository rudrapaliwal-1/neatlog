# SENTINEL-X Phase 3 security engineering report

Date: 2026-10-10. Scope: `backend/` only. No GitHub operations, repository cloning, or changes to `frontend/`, `agent/`, or `verification/`.

## 1. Baseline assessment and threat model

Before Phase 3 code edits, all existing backend modules and tests were inspected. Baseline command: `PYTHONDONTWRITEBYTECODE=1 /tmp/sentinel-x-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short`. Actual result: **28 passed, 0 failed, 0 skipped, 1 StarletteDeprecationWarning, 1.21 seconds**. `THREAT_MODEL.md` maps assets, trust boundaries, attack trees, STRIDE scenarios, privileged operations and residual risks. The strongest baseline control gaps were missing source-revision binding, incomplete success evidence, shared-token identity ambiguity, and no durable verification ownership.

## 2. Confirmed code-level weaknesses addressed

- A proposal and approval could remain actionable after target source or protected tests changed. Jobs now store a bounded full-tree revision; approval, verification and evidence recheck it. Stale pending jobs and active runs become execution errors.
- A verifier could report `PASSED` with nonzero counts but no suite identity, complete collection, run binding or source revision. Passing results now require all of these, and evidence independently checks persisted bindings and digest.
- Verification recovery previously treated every RUNNING row as interrupted at startup, including a second live instance. Leases preserve live work, expire abandoned work, and reject late results.
- State transitions relied on serialized writes without explicit expected-version checks. Transitions now use versioned compare-and-set in the same transaction as audit events.
- Approval records lacked explicit target/source binding and could be interpreted as individual identity. New bindings include target/revision/identity kind; the shared token is explicitly marked `DEMO_SHARED_TOKEN`.

These are demonstrated implementation gaps from the baseline review; no claim is made that an external attacker exploited them.

## 3. New controls

Server-owned `TargetManifest`; symlink/special-file rejection and 2,048-file/32-MiB snapshot bounds; revision checks; approval bindings; run/profile/suite attestation checks; digest recomputation; durable lease ownership/renewal; lease-aware startup recovery; SQLite quick and foreign-key checks; fail-closed production mode; readiness endpoint; correlation IDs, cache/security headers, and structured audit event fields. Direct dependencies and the local transitive environment are pinned in `requirements.txt` and `requirements.lock`; `sbom.spdx.json` inventories installed packages. `security_check.sh` is a reproducible local gate.

## 4. Tests added

23 new test cases (including parametrized variants) in `tests/test_phase3_security.py`: source/test drift, symlink rejection, incomplete and forged verifier success, zero collection, mismatched run/patch/revision/profile, evidence tampering, approval binding removal, live and expired lease behavior, active-run invalidation, SQLite contention, compare-and-set, malicious diff variants, planner context size, readiness and forensic headers. Existing verifier fakes were updated to the stricter trusted-output contract. Property-based testing was not added because the deterministic one-file parser has targeted negative cases and Hypothesis was not installed.

## 5. Actual validation

Run from project root:

| Check and exact command | Actual result |
|---|---|
| Baseline: `PYTHONDONTWRITEBYTECODE=1 /tmp/sentinel-x-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short` | 28 passed, 0 failed, 0 skipped, 1 warning, 1.21 s |
| Final gate: `PYTHON_BIN=/tmp/sentinel-x-venv/bin/python backend/security_check.sh` | AST parse passed; `pip check`: no broken requirements; 51 passed, 0 failed, 0 skipped, 1 warning, pytest 3.09 s; shell command 4.60 s |
| Secret-pattern scan: `rg -n -e 'BEGIN (RSA|EC|OPENSSH) PRIVATE KEY' -e 'AKIA[0-9A-Z]{16}' -e 'SENTINEL_OPERATOR_TOKEN=.{8,}' backend --glob '*.py' --glob '*.env' --glob '*.txt'` | No matches; `rg` exit 1 (limited source/config scan, not comprehensive secret scanning) |
| `/tmp/sentinel-x-venv/bin/python -m pip_audit --version` | Unavailable: `No module named pip_audit`; vulnerability audit not run |
| `/tmp/sentinel-x-venv/bin/python -m ruff --version` | Unavailable: `No module named ruff`; Ruff analysis not run |
| Local Uvicorn on `127.0.0.1:8765` with a temporary DB, test token and no configured adapters; `curl` to `/health`, `/ready`, and `/api/jobs` with/without token | `/health` 200; `/ready` 503 (expected because adapters absent); jobs without token 401; jobs with token 200 and `[]`. Initial connection attempts during startup failed, then succeeded on retry. |

The one test warning is Starlette's `httpx` TestClient deprecation. No dependency vulnerability conclusion can be drawn without an audit. The SPDX file lists the local environment, not a signed build artifact; version pins lack package hashes.

## 6. Contract changes and integration requirements

Public route paths, methods, finding/approval request bodies, response status semantics, and `/docs` remain. Approval responses add `identity_kind` and `source_revision`; job rows add `version`; evidence adds target binding and attestation details. The **trusted verifier adapter contract is intentionally stricter**: a passing `VerificationResult` must include suite identity, complete collection and execution flags, plus exact run ID, patch hash, source revision and verification profile echoes. Older Developer 3 adapters will fail closed as `EXECUTION_ERROR` until updated. Existing Phase 2 DB jobs without Phase 3 bindings cannot be reapproved or verified; re-ingest them after backup.

The actual Developer 3 verifier must independently run the server-authorized suite against an immutable checkout, enforce isolation and cancellation, and emit truthful collection/completion fields. The actual Developer 4 planner must be checked against the bounded context contract. An OIDC identity provider must implement the approval-principal boundary before production use.

## 7. Residual risk and production blockers

A compromised configured verifier can lie in its report; echoed IDs and SHA-256 digests do not authenticate it. A database or host administrator can rewrite records and digests. Filesystem revision checks cannot eliminate a concurrent host-level TOCTOU attack; immutable read-only snapshots are needed. In-process timeouts and DB leases cannot kill runaway Docker or child processes. The shared demo token cannot identify a human. No real agent/verifier Docker integration, external dependency audit, reverse proxy/TLS configuration, external rate limiter, off-host audit retention, backup restore drill, or production identity provider was available. **Do not expose this backend publicly or mark it production ready.** See `PRODUCTION_READINESS.md` for deployment gates and incident steps.

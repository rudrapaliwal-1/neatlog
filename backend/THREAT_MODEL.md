# SENTINEL-X backend threat model (Phase 3 baseline)

Baseline: 28 tests passed, 1 Starlette deprecation warning (`PYTHONDONTWRITEBYTECODE=1 /tmp/sentinel-x-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short`). Reviewed all backend Python modules and tests before Phase 3 changes.

## Assets and trust boundaries

Assets: authorized target source, approved patch bytes, approval decisions, verifier results, job state, SQLite evidence, operator token. HTTP findings and approval requests cross into the server; planner proposals cross from the AI adapter; source files cross from the configured target tree; verifier output crosses from the independent verifier adapter; SQLite persists the resulting state. The operator token authenticates a shared demo operator, not a human identity. The trusted computing base comprises server policy, workflow, configured integrations, database, host, and verifier isolation.

Privileged operations: create jobs, approve or reject patches, launch verification, advance state, and read patches/evidence. State-changing routes are `POST /api/findings`, `/api/jobs/{id}/approval`, and `/api/jobs/{id}/verify`. All `/api/` routes require the demo token; `/health` is public. The source tree and integration callables are configured by the server, not request payloads.

Untrusted input includes findings and descriptions (including prompt injection), AI explanations and diffs, retry feedback, request headers/bodies, and any content read from a target checkout. Agent or verifier compromise is in scope as a high-impact dependency failure. Recovery paths include planner/verifier exceptions, timeout, SQLite rollback, retry exhaustion and restart reconciliation.

## STRIDE and abuse cases

| Threat | Impact / likelihood / exploitability | Existing mitigation | Gap at baseline |
|---|---|---|---|
| Spoofed approval or replay | High / medium / medium | Shared token, patch hash, attempt and unique patch approval | No individual identity; no source revision binding |
| Tampered or malicious diff, traversal, protected tests, symlink | High / medium / medium | Strict one-file diff parser and path allowlist | Target filesystem revision and symlink status not bound |
| Forged or incomplete verifier success | Critical / medium / medium | Adapter boundary and count checks | No suite identity, complete collection or run binding |
| Concurrent state manipulation | High / medium / medium | SQLite `BEGIN IMMEDIATE`, unique patch/run | No explicit state compare-and-set or durable run ownership |
| Database tampering or repudiation | Critical / low / high with host access | FK pragma and append-only event triggers | Same host can rewrite DB/triggers; no external audit store |
| Prompt injection in finding/source | High / high / medium | AI output treated as proposal and policy checked | Compromised trusted adapter remains powerful |
| Resource exhaustion | Medium / medium / medium | body/patch/source limits, timeouts | In-process daemon calls cannot terminate runaway work |
| Dependency or secret compromise | Critical / low / medium | Import root restriction, token redaction | Broad dependency ranges; no audited deployment pipeline |

These are threat scenarios and baseline control gaps, not claims of a demonstrated exploit.

## Attack trees

**Reach VERIFIED without authorized repair:** forge an approval, replay an old approval, alter patch bytes after approval, replace target source after planning, forge verifier output, report zero or partial tests as success, or manipulate persisted state. Every route must require current patch, revision, approval and complete matching verifier evidence.

**Execute unauthorized content:** supply a malicious finding that steers the planner, craft diff traversal/duplicate headers/metadata/symlink targets, or compromise configured agent/verifier packages. Server-owned target manifest, deterministic diff policy, immutable revision binding and isolated verifier execution are needed.

**Lose evidence or availability:** race approvals/verification, crash during a run, lock the database, exhaust request resources, or modify SQLite directly. Atomic transitions, leases, startup reconciliation, backups and external monitoring are needed.

## Invariants and residual risk

Only server policy may authorize a target and patch path. An approval applies to one job, patch, attempt, digest and source revision. VERIFIED requires a matching completed verifier run with complete test collection. Every state change is atomic and audited. The AI cannot authorize or choose commands.

Residual risks: the shared demo token does not identify a person; SQLite event triggers do not resist host/DB administrator tampering; hashes detect mismatch but do not authenticate the verifier; source revision hashes cannot prevent a malicious host changing files after checks; in-process timeout does not kill a verifier subprocess; actual Developer 3/4 integrations and isolated execution are unavailable locally. Public production exposure remains blocked.

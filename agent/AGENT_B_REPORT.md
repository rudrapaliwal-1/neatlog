# Agent B integration report — 2026-10-10

## Phase 4 backend contract, inspected read-only

The integrated backend at `<local-path> /Agent-Solution--feat-verification/` is accessible. No files in that checkout were edited. `backend/services/agent_adapter.py` calls a configured public `agent.*` callable synchronously as:

```python
propose_patch(finding: dict, source_context: dict[str, str],
              attempt: int, feedback: dict | None = None) -> AgentProposal | dict
```

`backend/schemas.py` requires exactly `root_cause` (1–4000 characters), `explanation` (1–8000), `patch_format="unified_diff"`, `patch_text` (1–32768 valid UTF-8 characters), and `files_changed` (at most one path). Extra fields are forbidden. `backend/policy.py` further requires a valid Git unified diff of only `app/access.py`, a matching declared file list, and the server-owned patch size and revision policy. The backend calculates the patch hash and owns approval and verification state.

`backend/workflow.py` assigns attempt **0** to the initial proposal and **1–2** to revisions. Its retry payload has exactly:

```python
{"tests_total": int, "tests_failed": int, "failed_tests": list[str]}
```

It sanitizes names to `[A-Za-z0-9_./:-]`, truncates each to 128 characters, and sends at most 20 names. `backend/config.py` enforces two revisions. `source_context` is independently bounded to the authorized `app/access.py` source (16 KiB) by `bounded_source_context`.

The Phase 4 documentation in `backend/README.md`, `backend/INTEGRATION_READINESS.md`, `backend/PHASE4_INTEGRATION_REPORT.md`, and `verification/README.md` was inspected. The verifier is integrated, but this checkout does not contain the real Agent A planner.

## Agent B changes

- Aligned `build_revision_guidance(feedback: dict, attempt: int) -> str` with the exact backend retry payload and attempts 1–2. It rejects extra/free-form fields, malformed counts, oversized feedback, invalid identifiers, and attempts outside the backend range. It emits only fixed trusted instructions, counts, and bounded machine-readable identifiers. It never exposes protected test source, applies a patch, or approves a revision.
- Replaced the skipped backend contract placeholder with read-only tests importing the real backend schema, adapter, config, and patch policy. An AST assertion checks the backend's exact retry payload keys. Tests cover valid proposals and schema/policy mismatches. They do not claim to have run Agent A inference.
- Preserved the existing Neatlogs observer and event tests. Hosted tracing remains pending until `NEATLOGS_API_KEY` is configured securely.

## Interface to coordinate with Agent A

Agent A should expose a public configured `agent.*:propose_patch` callable with the backend signature above. At attempt 0, `feedback` is `None`; at attempts 1–2, call `build_revision_guidance(feedback, attempt)` and pass the returned string to Agent A's internal `generate_patch()` as diagnostic guidance. Keep the backend-provided `source_context` separate and authorized. Return the exact five-field proposal to the backend adapter; do not add approval or verification claims. The actual `generate_patch()` implementation was not present in either inspected checkout or found on this machine, so direct interface and inference validation is pending its path from the user.

## Environment and results

- Workspace-local CPython 3.12.15 and Neatlogs 1.4.26 are installed in `.venv`; uv 0.13.0 is under `.tools/uv`.
- Official local Neatlogs Doctor: **pass**, format `neatlogs.doctor/v2`, schema 2, four local spans, successful flush. This does not demonstrate hosted export or the application workflow.
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s agent/tests -v`: **22 passed, 0 failed, 0 skipped**.
- `NEATLOGS_API_KEY` remains unset. No authenticated Doctor probe or hosted trace was run, and no trace or inference result was fabricated.
- No backend, verification, or Agent A file was modified. No GitHub operations or pushes were performed.

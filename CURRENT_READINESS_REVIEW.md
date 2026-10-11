# SENTINEL-X local readiness review — 2026-10-11

## Decision

The next milestone is a reproducible fresh-model BOLA remediation through the dashboard: submit finding, generate a valid proposal, obtain human approval for its exact hash, run Docker verification, and inspect evidence. Do this before expanding vulnerability types or polishing the demo further.

The current application is a constrained BOLA remediation demonstration, not a general repository vulnerability scanner. Intake currently offers one predefined finding for `bola-demo-v1`; generation and policy are restricted to `app/access.py` and an ownership guard.

## Checks performed this review

- Reviewed frontend/API integration, model provider and guard parser, workflow/approval interfaces, verification runner, telemetry adapter, startup configuration, and existing test coverage. This is a practical readiness review, not a complete security certification.
- Confirmed Ollama lists `qwen2.5-coder:7b` (4.7 GB).
- Confirmed the Docker verifier image exists and the running backend health endpoint responds successfully.
- Frontend TypeScript check and Vite production build passed.
- Real model smoke test failed after 184.38 seconds with `GenerationError: Patch generation failed (EditError)`. No valid proposal artifact was produced by that run. The exact parser rejection is hidden by the current generator error wrapper and remains to be diagnosed.
- The authorized source has LF line endings, and a separate valid-guard source-anchor check passed. A Windows newline mismatch in this actual source is therefore not the explanation for that smoke failure.
- During the concurrent test run, free physical memory was approximately 430 MiB out of 15.9 GiB. Ollama reported a 5.1 GB loaded model with 88%/12% CPU/GPU placement. These observations indicate memory pressure; they do not isolate generation latency from competing test load.
- Full regression run: **169 passed, 9 failed, 32 subtests passed**, 245.21 seconds. Two failures are the known Windows CRLF fixture assertion and unavailable symlink privilege. Seven are Docker integration execution failures during concurrent inference. Log: `local-audit/current-review-tests.log`; JUnit: `local-audit/current-review-tests.xml`.
- Subsequent standalone Docker fixture diagnostic: correct fixture **VERIFIED, 8/8 passed**; incomplete fixture **VERIFICATION_FAILED, 5 passed / 3 failed**. These are prepared fixtures with automated test approval, not fresh-model or human-approved evidence. Latest results: `local-audit/docker-fixture-results.json`.
- Follow-up Docker integration subset without concurrent inference: **8 passed, 15 deselected**, 81.90 seconds. This subset includes all seven Docker failures from the earlier full run. The failures did not reproduce in this recheck; resource contention is a plausible explanation, not a proven root cause. Log: `local-audit/current-docker-recheck.log`.
- Fresh npm audit: **9 advisories — 5 high, 4 moderate**. Affected dependency chains include Tailwind and React Router. Several suggested fixes require major upgrades, so no forced upgrade was performed. Details: `local-audit/current-frontend-audit.json`.
- Hosted Neatlogs delivery and key validity were not verified in this review. Earlier local diagnostic success does not establish hosted delivery.

## Recommended work, in order

### 1. Make real generation reliable

Capture a safe, specific rejection category from `agent/edits.py` in the smoke diagnostic; inspect the model response locally without exposing secrets. Determine whether rejection is schema, AST, indentation, layout, or truncation. Keep the AST and policy restrictions intact. The configured 400-token output limit should be checked against actual completion metadata, not assumed to be the cause.

Repeat isolated inference to establish normal latency and success rate. Then run one complete browser workflow with a newly generated patch and explicit operator approval. Record generation duration, exact patch hash, Docker result, and evidence integrity. Do not represent a prepared fixture as a fresh AI result.

### 2. Establish stable laptop execution

Rerun the Docker tests without concurrent inference and investigate any reproducible failures. Measure the actual sequential generation-then-verification workflow. Avoid drawing conclusions solely from the overloaded concurrent audit.

### 3. Improve runtime diagnostics

`backend/main.py` `/ready` currently checks token, configured callables, and database access. It does not check model availability, Docker daemon/image availability, or the host patch executable. Add bounded dependency checks and expose actionable status in the UI. Token copying currently occurs before backend port binding succeeds, which can mislead the operator after a port conflict.

### 4. Finish telemetry and revision evidence

Validate hosted Neatlogs export using the configured key, then confirm a real application trace appears. `agent/planner.py` supplies attempt and model metadata but no job ID; the observer also drops initial attempt `0` because it accepts only attempts >= 1. Correct correlation before relying on the dashboard to diagnose multiple jobs. Demonstrate failure, bounded revision, and fresh approval with clearly labeled test evidence; a real-model revision demonstration remains unproven.

### 5. Fix small frontend workflow issues

- `frontend/src/components/Header.tsx` uses `window.location.href` for search. That reloads the page and clears the in-memory operator token, returning the user to connection login. Use router navigation.
- Dashboard and Findings fetch on mount/manual refresh; their list does not poll while planning is active. Investigation does poll. Make progress visibility consistent.
- Dashboard statistics use only the default first 100 jobs returned by the API. Add pagination/aggregate counts before presenting them as lifetime totals.
- The notification button has no action. Implement it or remove the affordance for the demo.

### 6. Clean up tests, dependencies, and handover

Make test fixture newlines explicit and run symlink security tests in a supported environment; do not weaken the source-byte integrity checks to satisfy a Windows assertion. Register the Docker test marker. Address dependency advisories with compatible upgrades where possible and planned major migrations where necessary. Update historical reports that still say the frontend or planner is absent. Keep production deployment out of scope until identity, durable execution, and operational controls are addressed.

## Change made during this review

Changed the real inference smoke script's output path from Unix `/tmp/...` to project-local `local-audit/real-ai-proposal.json` for Windows compatibility. The generation failure happened before that write, so successful artifact creation remains untested. No changes were made to the model guard acceptance rules or the live application workflow.

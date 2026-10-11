# Frontend local integration — 11 October 2026

The team's supplied React frontend is installed, integrated with the actual backend contract, builds successfully, and is serving locally at **http://localhost:5173**. The existing live backend at **http://127.0.0.1:8000** returned HTTP 200 from `/health` during the final check. The live frontend uses the real planner; it has no fixture fallback.

## Changes

- Added an operator-token connection screen. Token is kept only in JavaScript memory, sent as `X-Operator-Token` on `/api/` calls, and cleared on disconnect or page reload. No operator token is in Vite environment variables, source, logs, storage, or evidence exports.
- Mapped backend job `id` to the UI's `job_id`; mapped `patch_text` and `files_changed` into the diff viewer without changing the exact text or approval hash. Root cause comes from the proposal.
- Approval is enabled only for `AWAITING_APPROVAL` with a policy-passed patch. Explicit verification is enabled for the backend's `VERIFYING` state after approval and disabled during an active run. A revised patch with a different hash remains eligible for verification after fresh approval.
- Planning jobs without a proposal now display their job/events instead of failing the entire page on `/patch` 404. Investigation polls during planning/verification without resetting the visible page.
- Verification display uses actual persisted backend run evidence, including its run status and exact patch hash. Historical run evidence remains labeled as the latest completed verification run.
- Timeline consumes actual nested backend events, timestamps, state transitions, attempts and hashes.
- Increased verification-request timeout to 17 minutes to accommodate the configured Docker timeout plus possible model revision. No automatic POST retry was added.
- Restored missing layout rules for investigation, approval, verification, timelines and evidence while retaining the supplied dark editorial design. Corrected UTF-8 punctuation after a Windows editing encoding issue.
- Bound Vite to loopback. Added `scripts/start_local_frontend.ps1` and the backend launcher's optional `-CopyToken` switch.
- npm dependencies and lockfile installed. `npm audit fix` applied its compatible-resolution check; **9 advisories remain** in the supplied Tailwind 3 / React Router 6 dependency trees, with the registry proposing major upgrades. Those framework migrations were not forced into this integration. This report does not claim an audit-clean dependency tree.

## Verification executed

- `npm run build`: **passed**, including strict TypeScript checks and Vite production build. Final output approximately 220 kB JS / 68 kB gzip, 34 kB CSS / 8 kB gzip.
- Both PowerShell startup scripts parsed successfully.
- Live frontend HTTP 200 at port 5173; existing live backend health HTTP 200 at port 8000.
- Separate browser acceptance-test frontend on port 5174, clearly labeled **Fixture integration test — prepared patch, real Docker**, against an isolated real FastAPI backend on port 8001.
- Browser sequence: operator connection → submit BOLA finding → list actual job → open actual diff/root cause/events → approve exact hash → request real Docker verification → display **VERIFIED, 8 passed, 0 failed**, 14.912-second verifier duration → retrieve persisted evidence → disconnect.
- Test job: `job-<redacted-id>`.
- Prepared fixture patch hash: `sha256:dc2ecd6167df9d86ace539c25560774b79a1d9feeab661dbd6c041143364db86`.
- Displayed evidence conclusion `VERIFIED`, proposal hash integrity `VALID`, one exact-hash approval, run attestation integrity `VALID`, no integrity issues.
- Saved directly from displayed backend evidence: `local-audit/browser-fixture-evidence.json`; screenshot: `local-audit/frontend-docker-verification.png`. The separate test database is `local-audit/browser-fixture.db`.
- Temporary fixture-test services were stopped. Live frontend port 5173 and the user's backend port 8000 were left running.

These results establish a browser-to-backend-to-Docker workflow with a **prepared test patch**. They do not establish fresh model generation or real-model self-correction. No protected tests, approval policy, or production verifier source was changed.

## Use it now

Open **http://localhost:5173**. Connect with the operator token from the running backend session. If you need to copy it, stop the backend in its original PowerShell window with Ctrl+C, then from the project root run:

```powershell
& .\scripts\start_local_backend.ps1 -CopyToken
```

Paste the clipboard token into the connection screen and select **Connect to backend**. The token value is not printed or written to files. Clear the clipboard after connecting if desired.

To start the frontend again later, in a second PowerShell window from the project root:

```powershell
& .\scripts\start_local_frontend.ps1
```

Keep both services running. Reloading the frontend requires reconnection, because credentials are intentionally session-only. The last real inference audit found no Ollama models installed; download the configured model before expecting a newly submitted live finding to produce an AI proposal. Docker verification is operational as documented in `DOCKER_AUDIT_REPORT.md`.

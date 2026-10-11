# Final acceptance checklist — 11 October 2026

`PASS` refers only to executed evidence. `BLOCKED` denotes an external or approval gate. `NOT TESTED` is not counted as a pass.

| Criterion | Status | Evidence / limit |
| --- | --- | --- |
| Browser registration and login without backend token | PASS | Browser registered user A, later logged in through account form; no operator token entered. |
| Passwords not stored in plaintext | PASS | Argon2id hash in SQLite schema and auth implementation; password never returned by API. |
| Refresh retains valid session | PASS | Browser refreshed evidence page and remained authenticated. |
| Logout invalidates session | PASS | Browser returned to login; API test confirmed subsequent request gets 401. |
| Session expiry and CSRF | PASS | `backend/tests/test_product.py`: expired session gets 401; missing CSRF gets 403. |
| User A cannot read user B's project/job/evidence | PASS | API ownership tests and second-user browser check (`job not found`, empty project list). |
| ZIP upload, project list/details/status/files | PASS | Browser upload showed supported project, source revision and three source files. |
| Corrupt, traversal, absolute, duplicate, symlink, ZIP bomb rejection | PASS | Parameterized product tests returned 422 and left no extracted source. |
| Oversized raw archive request | PASS | Product test sent >10 MiB and received 422 with no extracted source. |
| Unsupported framework labelled honestly | PASS | Unsupported `main.js` archive imported as `UNSUPPORTED`; remediation gated. |
| Repository-wide vulnerability scanning | FAIL | No general scanner; finding is supplied for one contract. No scan claim is made. |
| Finding selection and real model patch | PASS | Browser job `job-aae4…` used genuine Qwen output; exact hash `sha256:27f634…9261b`; policy passed. |
| Exact historical EditError root cause | NOT TESTED | Saved raw response parsed successfully; original failing raw/error detail unavailable. Current fresh run succeeded after bounded timeout change. |
| Exact-hash human approval and stale/unapproved rejection | PASS | Browser approval bound user, patch and revision; existing approval tests plus product test rejecting unapproved verification. |
| Uploaded source verified in restricted Docker with trusted tests | PASS | Browser 8/8 `VERIFIED`; project-specific fixture positive/negative tests also ran in Docker. |
| Incorrect patch cannot be VERIFIED | PASS | Uploaded-project incomplete fixture produced 5 passed, 3 failed, `VERIFICATION_FAILED`. This was an API integration test, not Qwen browser output. |
| Persisted evidence integrity and per-test records | PASS | Browser evidence attestation was valid with `conclusion: VERIFIED`; later Docker tests asserted eight actual test records. |
| Browser shows actual verifier verdict | PASS | Job page showed `VERIFIED`, 8 passed, 0 failed and matching hash. New builds also display per-test names/outcomes. |
| Verifier failure is not shown as success | PASS | Negative Docker integration test returned `VERIFICATION_FAILED`; result was persisted as non-verified evidence. |
| Agent B bounded reflection and revision | PASS | Existing agent/backend regression tests cover fixture reflection and retry path. |
| Genuine model-driven Agent B recovery | NOT TESTED | No failed real-model attempt followed by a successful real-model revision was demonstrated. |
| Existing Neatlogs integration preserved | PASS | Existing observer and credential file untouched; local workflow events remain. |
| New hosted Neatlogs lifecycle events | BLOCKED | Automatic approval review rejected outbound telemetry changes as unapproved egress. No new export was installed. |
| Hosted Neatlogs delivery verified | NOT TESTED | No hosted dashboard access/probe in this run; configuration presence is not delivery proof. |
| Frontend type check and production build | PASS | `tsc --noEmit` and `vite build` executed on the final UI changes. |
| Full agent/backend/verifier regression suite | PASS | 190 passed, 0 failed, 0 skipped, 2 warnings and 32 subtests in 145.55 seconds; log at `local-audit/phase7-final-tests.log`. |
| General production readiness | FAIL | Production mode deliberately refuses startup; local controlled deployment only. |

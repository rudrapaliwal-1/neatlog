# Security architecture

## Flow and boundaries

`POST /api/findings` authenticates the demo token, validates the finding, authorizes the target with a server-owned manifest, and snapshots the configured target source tree. The planner receives bounded source context. Its result remains untrusted and passes strict schema and unified-diff policy before a proposal is persisted.

`POST /api/jobs/{id}/approval` compares the current source revision, job state, patch attempt and hash in a SQLite transaction. The approval binding records the target, revision and identity kind. `POST /api/jobs/{id}/verify` repeats these checks and creates one run and ownership lease. Only the configured independent verifier adapter receives the request and approval-verifier callback. A successful result must echo the exact run, patch hash, source revision and verification profile and report a complete required suite collection. The backend persists a digest over the run context and result before entering VERIFIED.

SQLite uses WAL, FULL synchronous writes, immediate write transactions, foreign keys, a unique run-per-patch index, versioned state compare-and-set, and append-only audit-event triggers. Startup performs critical object, foreign-key and quick integrity checks. Migrations add binding/lease/attestation tables and the job version column; existing jobs without Phase 3 bindings fail closed. Back up before upgrading a real database.

## Target manifest and source snapshot

`manifest.py` owns the single authorized target, patch allowlist, protected path categories, verification profile and format. For the integrated verifier, the revision hashes both the sorted target lab tree and configured protected tests tree, rejecting symlinks, special files and trees over 2,048 files or 32 MiB. It is a revision identifier, not an immutable filesystem. Use an immutable checkout or snapshot for the verifier. The configured source tree should exclude generated files and be mounted read-only; a changing source blocks success.

## Verifier integration contract

The configured `verification.*` callable must accept `VerificationRequest` (including run ID, attempt, revision and profile) and the approval-verifier callback. It must return `VerificationResult` with actual test counts, collection completeness, execution completion, suite identity and echoed run binding. It must independently choose and run the server-authorized suite in an isolated worker, apply the exact patch to the exact immutable revision, reject altered protected tests, and enforce OS/container resource limits. The Developer 3 verifier is integrated in Phase 4 and tested against real Docker runs; see PHASE4_INTEGRATION_REPORT.md. This is local integration evidence, not production isolation assurance.

The server-owned digest is an integrity checksum only. Signed attestations would require a separately managed verifier identity, protected private key, rotation, replay rules and independent validation; none are implemented.

## Concurrency and recovery

SQLite `BEGIN IMMEDIATE` serializes writers. Versioned job updates detect stale transitions. A run lease records owner, random token and expiry; the wait loop renews it at most every five seconds and before one third of its lifetime. A second backend instance leaves an unexpired run alone. Restart reconciliation marks expired or legacy unleased RUNNING runs and interrupted PLANNING jobs as execution errors. A late result is refused. No automatic duplicate launch occurs. A timed-out or crashed in-process adapter may keep a Docker or child process alive; operational isolation and cancellation must be supplied by the verifier.

## Authentication and API

`development` and `demo` are local modes with one shared operator token. `production` fails startup until real identity and isolation are implemented. The `ApprovalIdentityProvider` interface is the integration seam for OIDC subject and authorization claims; it is not an OIDC implementation. API docs remain at `/docs` to preserve the existing contract, but contain no job data. `/health` is liveness and `/ready` checks the database, demo token and configured adapters. The reverse proxy must enforce TLS, forwarded-header trust, external rate limits and network access rules. In-process rate limiting is intentionally absent.

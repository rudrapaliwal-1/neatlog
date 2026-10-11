# Production readiness and operations

**Status: blocked for public production exposure.** The demo token cannot identify an individual approver, the real planner is absent, and the local Docker verifier integration is not a production worker isolation review.

## Deployment checklist

- Put an OIDC identity provider and server-side role authorization in front of approval decisions. Persist stable human subject, issuer and authentication context; replace `DEMO_SHARED_TOKEN` semantics.
- Terminate TLS at a trusted reverse proxy; configure exact allowed origins, trusted forwarded headers, external rate limits and network isolation. Keep `/docs` internal if schema disclosure matters.
- Store tokens and integration secrets in a secret manager, rotate them, and never log credentials. Do not expose the SQLite file or target checkout through the web server.
- Run the verifier as a separate, sandboxed process/container with read-only immutable target revision and protected test suite, no arbitrary commands or network access, CPU/memory/time limits, and explicit cancellation/cleanup. Confirm exact patch application and test collection.
- Configure durable external monitoring for execution errors, expired leases, repeated policy rejections, readiness failures, integrity issues and unusual request rates. Export audit events to an append-only system outside the DB trust boundary with retention and access policy.
- Test restore, backup encryption and key access. Use a single SQLite writer host on local storage. Move to a transactional server database when multiple hosts, higher write throughput, robust work queues or stronger audit isolation are required.
- Audit pinned dependencies in the deployment environment; verify package provenance and maintain an updated SBOM. Local versions are pinned, but hashes and vulnerability audit are not yet available.

## Backup and restore

Quiesce job creation/verification or use SQLite's online backup API from a read connection. Never copy only the main `.db` file while WAL writes are active. Store a timestamped encrypted backup outside the host. Restore into a new directory, run `PRAGMA quick_check` and `PRAGMA foreign_key_check`, then start the backend and inspect `/ready` and evidence for representative jobs. Practice recovery and define RPO/RTO with operators before production use.

## Migration and incident response

Back up the Phase 2 database before first Phase 3 startup. Schema creation and new-column migration run in one SQLite transaction. Legacy jobs lack source and approval bindings and therefore cannot reach VERIFIED under Phase 3; re-ingest findings. Roll back code only with a restored compatible database copy, not an in-place schema downgrade.

For suspected compromise: isolate the API and verifier worker, preserve SQLite database plus WAL and external logs, rotate the demo token and integration secrets, collect correlation IDs and job/patch/run identifiers, compare the source revision and evidence digests, and review approval decisions. Do not treat SQLite audit triggers or hashes as proof against host administrator tampering.

## Failure modes

Missing source, symlinks, oversize snapshot, changed source, invalid or incomplete verifier output, database integrity failure and missing production identity all fail closed. A verifier timeout ends the backend wait but cannot stop arbitrary child execution. A running lease is preserved on another instance's startup; an expired lease becomes an execution error on reconciliation. No durable queue or automatic retry exists. The real Docker verifier passed local Phase 4 integration tests; its deployment isolation, lifecycle and source immutability still need review. The real planner and production approval provider remain unintegrated.

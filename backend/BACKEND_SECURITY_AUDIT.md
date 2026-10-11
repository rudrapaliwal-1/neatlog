# Backend security audit — Phase 2

Scope: the existing `backend/` implementation, local single-operator mode, SQLite, and the current HTTP and adapter boundaries. This review used the [OWASP ASVS 5.0](https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en) themes of authentication, access control, input validation, secure configuration, error handling, and data integrity as a checklist. It is a code review and targeted test exercise, not an ASVS certification or penetration test.

## Confirmed issues corrected

| Area | Before | Correction and evidence |
| --- | --- | --- |
| Authorization | `POST /api/findings` and all job, patch, event, and evidence reads had no authentication. | All application `/api/` routes now require the configured local operator token (CORS preflight `OPTIONS` is exempt); health and Swagger stay public. Missing token closes access by default. Authentication tests cover every route. |
| Resource limits | Incoming finding bodies were not capped before JSON parsing. | An ASGI guard caps POST bodies at 16 KiB by default, checks `Content-Length`, and bounds streamed bodies before parsing. Schema fields and verifier result arrays are bounded. Oversized request tests return 413 without echoing input. |
| Input validation | Pydantic accepted undeclared fields and loose strings; the patch parser accepted unsupported metadata and mismatched hunk counts. | Strict models reject extra fields and wrong types; the policy parses only the one allowlisted Git unified diff, validates hunk counts, path headers, operations, encoding, and size. Malformed and protected-path tests cover this. |
| Dynamic imports | A configured `module:function` could import any Python module. | Configuration and the runtime loader restrict public callables to `agent.*` and `verification.*`. The modules themselves remain trusted code and must be controlled by deployment. |
| Approval binding | Approval was bound through a patch ID but did not store the attempt explicitly. | Approval records now store the attempt; active lookup checks job, patch, attempt, current state, exact hash, and recomputed patch bytes. Existing databases receive a backfilled `attempt` column. |
| Evidence integrity | `conclusion: VERIFIED` depended only on job status, so a tampered database could yield a misleading report. | Evidence reads a single SQLite snapshot and derives its conclusion from an intact current patch, policy pass, matching approval, and matching passing test record. Hash mismatches appear in `integrity_issues`. |
| Audit changes | Workflow events could be modified or deleted through a direct database connection. | SQLite triggers reject UPDATE and DELETE of workflow events. This protects against accidental application-level modification, not a database owner. |
| Error exposure | Framework validation errors could expose submitted values; trusted verifier `execution_error` text was returned and persisted raw. | Validation responses include field locations and error types without inputs. Verifier error text is reduced to a generic message; unexpected errors return a generic 500 and do not log request data. |
| Configuration | Short shared tokens and wildcard/non-local HTTP CORS origins were accepted. | Tokens must be 32–256 ASCII characters when configured. CORS accepts one exact HTTP(S) origin; non-local origins require HTTPS. The API is closed when no token is configured. |
| SQLite concurrency | The database used busy timeouts but no WAL mode or database uniqueness for verification runs. | WAL, synchronous FULL, snapshot reads, and a unique index on verification `patch_id` reinforce the existing `BEGIN IMMEDIATE` transactions. Concurrent approval and verification tests cover one-winner behavior. |

## Checks with no confirmed exploit in this audit

- **SQL injection:** all queries involving job IDs, hashes, and input values use SQLite parameters. Schema and PRAGMA statements are constant strings.
- **Workflow bypass:** public routes call the transition-checked workflow. No direct status setter is exposed. Approval and verification duplicate calls are rejected.
- **Patch hash calculation:** the pre-existing SHA-256 function hashes exact UTF-8 patch bytes. Phase 2 added active-approval and evidence recomputation checks.
- **AI execution:** the backend does not apply a patch or run an AI-supplied command. The verifier is the execution boundary.
- **CORS:** the pre-existing default listed one local origin; the risk was unvalidated configuration and unauthenticated endpoints, not the default origin itself.

## Remaining risks and limits

1. A shared development token is one operator credential, not individual identity, MFA, fine-grained authorization, rotation, or rate limiting. Frontend integration must avoid baking it into a public bundle. Use a real authentication design before network deployment.
2. SQLite files, findings, patch text, and evidence are not encrypted or cryptographically tamper-evident. A filesystem owner can alter records and remove triggers. Set restrictive file permissions and add independent signed audit storage for deployment.
3. The verifier must independently validate the patch and approval reference immediately before applying it. Backend policy does not make arbitrary runner behavior safe.
4. Timeouts stop the workflow waiting, but a timed-out in-process verifier thread may continue external work. A cancellable isolated worker is needed for stronger execution control.
5. Startup recovery assumes one backend process. Multiple workers sharing the same SQLite database can misclassify another worker's active job as interrupted. Run one worker for the demo.
6. A pending approved job remains `VERIFYING` until an authenticated `POST /verify` call. This is an explicit operational dependency.
7. Integration modules under the trusted prefixes execute Python at import. Their source, package path, and dependencies must be reviewed and controlled before configuration.
8. The parser intentionally accepts only one path and a narrow unified-diff syntax. Developer 3's runner must enforce at least the same target and path restrictions; the real contract and Docker behavior are still untested.
9. No end-to-end LLM plus independent Docker verifier test has run because those components are not available in this local workspace.
10. Findings are untrusted instructions to the planner; deterministic patch policy limits effects but cannot guarantee the LLM proposal is semantically safe.
11. Dependency ranges are not locked to hashes. Reproducible deployment needs pinned, reviewed dependencies and a vulnerability review.

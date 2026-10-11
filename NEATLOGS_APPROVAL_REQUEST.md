> Superseded on 11 October 2026 by the user-authorized nine-event scope in `NEATLOGS_FINAL_INTEGRATION_REPORT.md`. The two Agent B reflection events and database job IDs proposed below were **not** included in the final exporter. This file is retained as historical context.

# Owner approval request — new Neatlogs lifecycle telemetry

**Decision requested:** May SENTINEL-X transmit the following new lifecycle trace events to Neatlogs? No new lifecycle event export is enabled now. A yes authorizes only the payload and destination described below; it does not authorize prompts, source, diffs, findings, credentials or logs.

**Destination:** The current Python SDK integration has no endpoint override. Its [documented default](https://docs.neatlogs.com/sdk/python) is `https://ingest.neatlogs.com/v1/traces` over HTTPS. An EU project would require a separately configured `https://eu.ingest.neatlogs.com` base; that is not configured here.

**Event names (fixed vocabulary):** `project.uploaded`, `finding.submitted`, `agent.inference.started`, `agent.inference.completed`, `patch.generated`, `patch.validation.completed`, `approval.recorded`, `verification.started`, `verification.completed`, `agent.reflection.started`, `agent.reflection.completed`.

**Allowed application fields:** `event`; opaque `job_id` and `run_id` only when available; integer `attempt` (including 0); fixed `outcome`; bounded integer `tests_total`, `tests_passed`, `tests_failed`, and `duration_ms`. The SDK/transport may add trace and span identifiers, timing and standard network metadata. No usernames, emails, project ID/name, source code, patch text, prompts, raw finding descriptions, repository paths, tokens or test logs are in the proposed formatted fields.

**Identity and privacy:** Job/run IDs are random opaque identifiers but can be joined to specific users and projects by a party with access to the local database. They are pseudonymous, not anonymous. Neatlogs receives data as a third party. The project-specific retention period, residency and physical deletion guarantee have not been verified; obtain the owner’s Neatlogs agreement before enabling export.

**Current state:** The local formatter and tests are complete. It has no exporter. Existing Agent A Neatlogs integration is unchanged; hosted delivery for new categories is unverified. After explicit approval, implement the narrow exporter, test failure isolation, perform one minimal hosted delivery and record the trace ID and timestamp without disclosing the key.

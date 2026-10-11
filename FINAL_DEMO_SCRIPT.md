# Three-minute SENTINEL-X demo script

**Before the timed presentation:** Start the local backend, Ollama, Docker and frontend using `FINAL_DEMO_RUNBOOK.md`. Run a genuine Qwen proposal and wait until its job reaches `AWAITING_APPROVAL`; keep that unapproved browser job open. Have the fresh Phase 8 evidence record available. Do not present a fixture as model output.

**0:00–0:25 — Problem and boundary.** “A document endpoint can return another user's private record. SENTINEL-X accepts an authorized repository ZIP and a BOLA finding. It does not claim to scan arbitrary repositories.” Show the uploaded project's supported contract, source revision and source file list.

**0:25–0:55 — Local AI proposal.** Open the job. Show that Qwen produced the actual diff, explanation and SHA-256 hash. Point out the restricted one-file patch policy. The model is a proposer; its output does not become a security verdict.

**0:55–1:20 — Human control.** Review the exact diff and click **Approve patch** during the demo. State that this approval binds the current user, patch hash, attempt and source revision. Click **Request verification**. Do not auto-approve.

**1:20–2:10 — Independent proof.** Show the Docker result and each protected test. A VERIFIED status requires all eight tests passing. Open the evidence report to show the persisted run ID, hash, source revision and attestation. Refresh and show that the evidence remains.

**2:10–2:40 — Failure and recovery honesty.** Show the separately labeled controlled fixture run: the incomplete patch failed 3 of 8 protected tests. Its sanitized failure feedback triggered Agent B and a fresh proposal that required a second approval. This demonstrates wiring, not a naturally failed Qwen patch. If a genuine failed Qwen run was not observed, state that real model-driven recovery remains partial.

**2:40–3:00 — Isolation and limits.** Show that a second account has no access to the first account's project or evidence. State that Neatlogs lifecycle export remains gated on owner approval; local events work. Conclude: the core controlled BOLA workflow is ready for a local hackathon demo, while production deployment and broader repository coverage are outside scope.

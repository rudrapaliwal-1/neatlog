# SENTINEL-X — Entire CLI Integration Guide

This guide describes the integration of the official **Entire CLI** ([https://entire.io](https://entire.io), repository: [https://github.com/entireio/cli](https://github.com/entireio/cli)) with **SENTINEL-X** for AI-assisted development session provenance, Git checkpointing, and auditability.

---

## 1. What Entire Does and Does Not Do

### What Entire Does in SENTINEL-X
- **Developer Session Provenance**: Captures developer and AI agent interactions (prompts, tool calls, and diffs) during development in Antigravity.
- **Git Commit Association**: Automatically links captured agent sessions to standard Git commits via `Entire-Checkpoint` trailers and isolated Git refs (`refs/entire/checkpoints/` backend).
- **Searchable Audit Trail**: Provides semantic and keyword search across historical agent sessions, commits, and reasoning paths (`entire search`, `entire checkpoint explain`).
- **Fail-Safe Secret Redaction**: Intercepts transcripts before persistence to redact credentials, tokens, and database connection strings using built-in multi-pass scanners (e.g., Betterleaks).

### What Entire Does NOT Do
- **Not a Runtime Verifier**: Entire is strictly a development provenance tool. It does **not** evaluate patches, execute tests, or certify patch correctness.
- **Does Not Modify Runtime Pipeline**: Entire does **not** alter or replace `agent/planner.py`, `agent/generator.py`, `backend/workflow.py`, `backend/approvals.py`, `verification/patch_validator.py`, `verification/runner.py`, or `verification/evaluator.py`.
- **Not Verification Evidence**: Entire session history is developer telemetry, **not** proof that a patch passed the protected Docker sandbox test suite. It is not persisted in the SENTINEL-X verification database.
- **No Infallible Redaction**: Text scanners do not perform OCR on pasted screenshots or binary images. Any image pasted into an agent chat containing secrets will be saved unredacted in checkpoint assets.

---

## 2. Prerequisites and Installation

### Official CLI Installation

#### Windows (PowerShell)
Install the official stable release to `%USERPROFILE%\.local\bin` using PowerShell (no administrator privileges required):

```powershell
irm https://entire.io/install.ps1 | iex
```

Verify the installation:
```powershell
entire version
```

#### Linux / macOS / WSL
The Entire CLI can be installed from the official stable release channel into the user directory:

```bash
curl -fsSL https://entire.io/install.sh | bash -s -- --channel stable
```

The binary installs to `~/.local/bin/entire` along with `~/.local/bin/git-remote-entire`. Ensure `~/.local/bin` is in your `$PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
entire version
```

### Git Repository Requirement
Entire operates strictly on Git repositories. The repository must have an initialized `.git` directory before enabling:

```bash
# Verify Git root
git rev-parse --show-toplevel
```

---

## 3. Enabling Entire for Antigravity

To enable Entire for Antigravity while keeping checkpoints and session data strictly **local-only** (preventing automatic remote publishing):

```bash
entire enable --agent antigravity --skip-push-sessions
```

### What This Configures
1. **Antigravity Hooks** (`.agents/hooks.json`):
   Registers hooks for Antigravity's lifecycle events:
   - `PreInvocation`: Invokes `entire hooks antigravity pre-invocation`
   - `PreToolUse`: Invokes `entire hooks antigravity pre-tool-use`
   - `Stop`: Invokes `entire hooks antigravity stop`
2. **Project Settings** (`.entire/settings.json`):
   ```json
   {
     "enabled": true,
     "strategy_options": {
       "push_sessions": false
     },
     "checkpoints": {
       "primary": {
         "type": "git-refs"
       }
     }
   }
   ```
3. **Git Hooks** (`.git/hooks/`):
   Installs `prepare-commit-msg`, `commit-msg`, `post-commit`, `post-rewrite`, and `pre-push` hooks. These hooks check `command -v entire` and safely chain without breaking existing Git workflows.
4. **Local Ignores** (`.entire/.gitignore`):
   Automatically ignores `tmp/`, `settings.local.json`, `metadata/`, `logs/`, and `redactors/local/`.

---

## 4. Privacy, Redaction, and Checkpoint Storage

### Checkpoint Storage Models
- **Option A: Local-Only (Default Recommended)**:
  `push_sessions: false` ensures that session transcripts and checkpoint refs remain purely local on the developer workstation. No transcripts are pushed to upstream or origin Git remotes during normal `git push`.
- **Option B: Dedicated Private Checkpoint Remote (Requires Approval)**:
  If a dedicated private repository is created for team checkpoint storage:
  ```bash
  entire configure --checkpoint-remote github:<organization>/<private-checkpoints-repo>
  ```
  *Never configure a public repository or push without organizational review.*

### Redaction Boundaries
- **Built-in Redaction**: Multi-pass pattern scanners (Betterleaks, entropy analysis, URI credentials, connection strings) replace detected tokens with `REDACTED`.
- **Pasted Images / Assets**: Images are stored unredacted under `.entire/metadata/<session>/assets/`. **Never paste screenshots containing passwords, tokens, or credentials into the agent chat.**
- **Project Files**: Ensure root `.gitignore` excludes `.env`, `backend/*.db`, `local-audit/`, and `.entire/settings.local.json`.

---

## 5. Inspection, Diagnostics, and Troubleshooting

### Status and Health Checks
```bash
# Check Entire status and enabled configuration
entire status --detailed

# Check registered agents
entire agent list

# Run diagnostic scan (checks hook drift, stuck sessions, metadata integrity)
entire doctor
```

### Session and Checkpoint Commands
```bash
# Show active session for current worktree
entire session current

# List recent recorded sessions
entire session list

# View details for a specific session
entire session info <session-id>

# List checkpoints on the current branch
entire checkpoint list

# Explain the AI reasoning and commits for a checkpoint
entire checkpoint explain <commit-sha>

# Search checkpoints and sessions
entire search "<search-query>"
```

### Resuming or Stopping Sessions
```bash
# Stop active tracking session
entire session stop

# Resume session from a branch
entire session resume <branch-name>
```

---

## 6. Disabling or Removing Entire

If you need to deactivate Entire temporarily or permanently:

```bash
# Temporarily disable Entire session tracking in repository
entire disable

# Remove Antigravity agent hooks
entire agent remove antigravity

# To completely remove Entire configuration:
rm -rf .entire .agents/hooks.json
```

Existing Git source history and commits remain completely unaffected.

---

## 7. SENTINEL-X Runtime Verification Invariant

Entire operates completely outside the SENTINEL-X security architecture:
1. **No Runtime Dependencies**: Neither FastAPI (`backend/`), nor the AI planner (`agent/`), nor Docker verification (`verification/`) depends on or imports the Entire CLI.
2. **Protected Test Suite**: Verification tests in `verification/tests/` and backend security suites in `backend/tests/` remain the single source of truth for patch validation and BOLA enforcement.
3. **Execution Integrity**: Run existing tests at any time to confirm zero regressions:
   ```bash
   PYTHONPATH=. pytest agent/tests backend/tests verification/tests -q
   ```

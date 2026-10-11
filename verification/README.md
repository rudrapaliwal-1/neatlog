# SENTINEL-X — Independent Verification Engine (Developer 3)

**Tagline**: *"Don't just generate a fix. Prove that it works."*  
**Team**: BeyondSight — neatHack 2026  
**Ownership Boundary**: `verification/` (Phase 4 contract coordinated with `backend/`)
**Module version**: Developer 3 Layer 5; no semantic version is declared in the package.

---

## 1. Overview & Architecture

Developer 3 implements Layer 5 (**Restricted Verification Subsystem**). It provides an independent, non-LLM, deterministic verification engine that tests candidate AI patches against an intentionally vulnerable Broken Object-Level Authorization (BOLA) lab application within disposable, unprivileged Docker containers.

```
FastAPI Orchestrator (Dev 1)
   │
   ▼ ConfiguredVerificationAdapter (SENTINEL_VERIFIER_CALLABLE=verification.adapter:verify_backend_patch)
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ verification.adapter:verify_backend_patch(request, approval_verifier)                 │
│                                                                                        │
│ 1. Backend 4-Arg Callback Adaptation: approval_verifier(job, patch, hash, approval)    │
│ 2. Fail-Closed Security Gate: Validates approval before any workspace or container     │
│ 3. PatchValidator: Validates unified diff syntax, SHA-256 hash, size & scope          │
│ 4. Workspace Isolation: Creates ephemeral copy of clean baseline                       │
│ 5. Restricted Docker Sandbox: Runs pytest against protected tests in isolation         │
│    ├── Flags: --network none, --cap-drop ALL, --security-opt no-new-privileges        │
│    ├── Resources: --memory 512m, --cpus 1.0, --pids-limit 64                         │
│    └── Mounts: Protected tests mounted strictly READ-ONLY (:ro)                        │
│ 6. TestResultEvaluator: Deterministically evaluates report and emits structured verdict │
│ 7. Backend Schema Translation: Maps to PASSED/FAILED/EXECUTION_ERROR + count consistency │
└────────────────────────────────────────────────────────────────────────────────────────┘
   │
   ▼ VerificationResult (status: PASSED|FAILED|EXECUTION_ERROR, tests_total, tests_passed, tests_failed, ...)
FastAPI State Machine (Dev 1) / Persistence in SQLite
```

---

## 2. Directory Structure

```text
verification/
├── __init__.py                  # Public exports: verify_backend_patch, verify_patch, contracts
├── adapter.py                   # FastAPI backend compatibility adapter (verify_backend_patch)
├── contracts.py                 # Pydantic/Dataclass contracts & Status enums
├── runner.py                    # Ephemeral Docker sandbox runner controller
├── evaluator.py                 # Independent deterministic result evaluator
├── patch_validator.py           # Patch safety, scope, path traversal & hash binding
├── Dockerfile                   # Disposable lab container specification
├── requirements.txt             # Python dependencies (pytest)
├── README.md                    # Module documentation & integration guide
├── lab/
│   └── app/
│       ├── __init__.py
│       ├── access.py            # Target BOLA authorization logic (get_document)
│       └── sample_data.py       # Deterministic multi-tenant document store
├── protected_tests/
│   ├── __init__.py
│   ├── conftest.py              # Structured JSON report hook
│   ├── test_security.py         # Immutable adversarial security tests (BOLA exploits)
│   └── test_functional.py       # Immutable functional & regression tests
├── fixtures/
│   ├── incomplete_patch.diff    # Superficial fix fixture (fails security tests)
│   └── correct_patch.diff       # Comprehensive fix fixture (passes all 8 tests)
└── tests/
    ├── __init__.py
    ├── test_backend_adapter.py  # Unit & Docker tests for backend integration adapter
    ├── test_patch_validator.py  # Unit tests for patch validation & security rules
    ├── test_evaluator.py        # Unit tests for independent result evaluation
    └── test_runner.py           # Live Docker integration tests for all patch scenarios
```

---

## 3. Backend Integration Configuration

To integrate with Developer 1's FastAPI backend, configure the environment variable:

```bash
export SENTINEL_VERIFIER_CALLABLE="verification.adapter:verify_backend_patch"
export SENTINEL_SOURCE_ROOT="$PWD/verification/lab"
export SENTINEL_PROTECTED_TESTS_ROOT="$PWD/verification/protected_tests"
```

### Callable Signature
```python
verify_backend_patch(
    request: VerificationRequest,
    approval_verifier: Callable[[str, str, str, str], bool]
) -> dict
```

### Backend Request Schema
| Field | Type | Description |
|---|---|---|
| `job_id` | `str` | Job identifier |
| `target_app_id` | `str` | Authorized target (must be `"bola-demo-v1"`) |
| `patch_id` | `str` | Patch identifier |
| `patch_text` | `str` | Exact unified-diff patch string |
| `patch_hash` | `str` | `sha256:<64-hex-digits>` |
| `approval_id` | `str` | Active operator approval identifier |
| `attempt` | `int` | Current patch attempt |
| `source_revision` | `str` | Exact approved target and protected-suite revision |
| `verification_profile` | `str` | Server-owned `bola-required-tests-v1` profile |
| `run_id` | `str` | Exact backend verification run |

### Status Mapping & Count Invariants
| Verification Engine Status | Backend Status | Backend Rules Satisfied |
|---|---|---|
| `VERIFIED` | `PASSED` | Required eight-test inventory, complete collection, 8/8 pass, matching job/patch/hash/run/revision/profile |
| `VERIFICATION_FAILED` | `FAILED` | Required suite collected and executed, consistent counts, at least one failed test |
| `EXECUTION_ERROR` | `EXECUTION_ERROR` | `execution_error is not None` |
| `POLICY_REJECTED` | `EXECUTION_ERROR` (Fail-closed) | `execution_error is not None`, `tests_total == 0` |

---

## 4. Running the Backend with Integrated Verification

### Environment Setup:
```bash
export PYTHONPATH="$PWD"
export SENTINEL_DB_PATH="$PWD/backend/sentinel.db"
export SENTINEL_SOURCE_ROOT="$PWD/verification/lab"
export SENTINEL_PROTECTED_TESTS_ROOT="$PWD/verification/protected_tests"
export SENTINEL_FRONTEND_ORIGIN="http://localhost:5173"
export SENTINEL_OPERATOR_NAME="local-operator"
read -rsp 'Local operator token (32+ ASCII characters): ' SENTINEL_OPERATOR_TOKEN
echo
export SENTINEL_OPERATOR_TOKEN
export SENTINEL_VERIFIER_CALLABLE="verification.adapter:verify_backend_patch"
export SENTINEL_AGENT_CALLABLE="agent.planner:propose_patch"  # configure only when agent/ is supplied
```

### Starting the FastAPI Server:
```bash
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

---

## 5. Running Verification Tests

### Run all verification unit and integration tests (69 tests after Phase 4):
```bash
python3 -m pytest verification/tests/ -v
```

### Run complete test suite (verification + backend tests, 123 tests after Phase 4):
```bash
python3 -m pytest verification/tests/ backend/tests/ -v
```

### Rebuild Docker verification lab image:
```bash
docker build -t sentinel-verification-lab:latest -f verification/Dockerfile verification/
```

## Phase 4 evidence contract

`verify_backend_patch` rejects missing or mismatched run, attempt, profile, patch hash and source revision before launching Docker. The revision includes both `verification/lab` and `verification/protected_tests`. The evaluator derives `test_suite_id`, `tests_collected`, `collection_complete` and `execution_completed` from the actual protected pytest report; the adapter does not fill missing evidence with guessed values. The adapter checks exact returned job, patch, hash and run IDs and rechecks source revision after execution. The canonical fixtures now satisfy the backend's strict git unified-diff policy. See `backend/PHASE4_INTEGRATION_REPORT.md` for actual Docker and backend results.

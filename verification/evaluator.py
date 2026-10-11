"""Independent Test Result Evaluator for SENTINEL-X Verification (Layer 5).

Strictly evaluates test runner output without LLM subjectivity:
- VERIFIED is returned ONLY if all required protected tests execute and pass.
- Missing test collections, timeouts, report tampering, and infrastructure crashes produce EXECUTION_ERROR.
- Policy and approval failures produce POLICY_REJECTED / fail-closed errors.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from .contracts import VerificationResult, VerificationStatus


class TestResultEvaluator:
    """Deterministic, tamper-resistant evaluator for verification test reports."""

    # Expected minimum test count for full coverage
    MIN_REQUIRED_TESTS = 8
    TEST_SUITE_ID = "bola-required-tests-v1"

    # Required immutable test identifiers from protected_tests suite
    REQUIRED_TEST_NAMES: Set[str] = {
        "test_owner_accesses_own_document_successfully",
        "test_anonymous_user_cannot_access_private_documents",
        "test_nonexistent_document_handled_correctly",
        "test_legitimate_functionality_remains_intact",
        "test_user_a_cannot_access_user_b_document",
        "test_user_b_cannot_access_user_a_document",
        "test_multiple_unauthorized_document_ids_rejected",
        "test_superficial_fix_blocking_only_single_id_rejected",
    }

    @classmethod
    def evaluate(
        cls,
        job_id: str,
        patch_hash: str,
        exit_code: int,
        raw_output: str,
        report_json_str: Optional[str] = None,
        duration_ms: int = 0,
        timed_out: bool = False,
        runner_error: Optional[str] = None,
        run_id: Optional[str] = None,
        patch_id: Optional[str] = None,
    ) -> VerificationResult:
        """Evaluate runner outputs and produce a structured, tamper-proof VerificationResult."""

        # 1. Timeout Check
        if timed_out:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                execution_error="Execution timed out in sandbox environment.",
                run_id=run_id,
                patch_id=patch_id,
            )

        # 2. Runner Crash / Infrastructure Error Check
        if runner_error:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                execution_error=f"Runner error: {runner_error}",
                run_id=run_id,
                patch_id=patch_id,
            )

        # 3. Report Missing / Malformed Check
        if not report_json_str or not report_json_str.strip():
            err_msg = f"Test report missing or runner exited prematurely with code {exit_code}."
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                execution_error=err_msg,
                run_id=run_id,
                patch_id=patch_id,
            )

        try:
            report_data = json.loads(report_json_str)
            if not isinstance(report_data, dict):
                raise ValueError("Report root must be a JSON object")
        except Exception as exc:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                execution_error=f"Malformed report JSON: {exc}",
                run_id=run_id,
                patch_id=patch_id,
            )

        summary = report_data.get("summary", {})
        tests_data = report_data.get("tests", [])

        if not isinstance(summary, dict) or not isinstance(tests_data, list):
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                execution_error="Invalid report schema structure.",
                run_id=run_id,
                patch_id=patch_id,
            )

        # Compute counts directly from individual test records for tamper resistance
        recorded_total = len(tests_data)
        recorded_passed = sum(1 for t in tests_data if isinstance(t, dict) and t.get("outcome") == "passed")
        recorded_failed = sum(1 for t in tests_data if isinstance(t, dict) and t.get("outcome") == "failed")
        recorded_errored = sum(
            1 for t in tests_data if isinstance(t, dict) and t.get("outcome") not in ("passed", "failed", "skipped")
        )

        total = summary.get("total", recorded_total)
        passed = summary.get("passed", recorded_passed)
        failed = summary.get("failed", recorded_failed)
        errored = summary.get("error", recorded_errored)

        # Reconcile summary with test record counts
        if total != recorded_total or passed != recorded_passed or failed != recorded_failed:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                duration_ms=duration_ms,
                execution_error="Evidence tampering detected: summary counts mismatch individual test records.",
                run_id=run_id,
                patch_id=patch_id,
            )

        # Extract failed test identifiers
        failed_tests: List[str] = []
        executed_test_functions: Set[str] = set()
        test_results: List[Dict[str, str]] = []

        for t in tests_data:
            if not isinstance(t, dict):
                continue
            nodeid = str(t.get("nodeid", ""))
            outcome = t.get("outcome")
            func_name = nodeid.split("::")[-1] if "::" in nodeid else nodeid
            executed_test_functions.add(func_name)
            if outcome in ("passed", "failed", "error", "skipped"):
                import re
                safe_name = re.sub(r"[^A-Za-z0-9_./:\-\[\]]", "_", nodeid)[:128]
                test_results.append({"name": safe_name, "outcome": outcome})

            if outcome in ("failed", "error"):
                failed_tests.append(nodeid)

        # 4. Zero or Insufficient Tests Collected Check
        if total == 0 or total < cls.MIN_REQUIRED_TESTS:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                tests_total=total,
                tests_passed=passed,
                tests_failed=failed + errored,
                failed_tests=failed_tests,
                duration_ms=duration_ms,
                execution_error=f"Incomplete test execution: collected {total} tests (minimum {cls.MIN_REQUIRED_TESTS} required).",
                run_id=run_id,
                patch_id=patch_id,
            )

        # 5. Required Protected Test Suite Inventory Check (Anti-Evasion)
        missing_required = cls.REQUIRED_TEST_NAMES - executed_test_functions
        if missing_required:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                tests_total=total,
                tests_passed=passed,
                tests_failed=failed + errored,
                failed_tests=failed_tests,
                duration_ms=duration_ms,
                execution_error=f"Required protected security test(s) not executed: {sorted(missing_required)}",
                run_id=run_id,
                patch_id=patch_id,
            )

        skipped = summary.get("skipped", 0)
        if skipped or passed + failed + errored != total:
            return VerificationResult(
                job_id=job_id, patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                tests_total=total, tests_passed=passed, tests_failed=failed + errored,
                failed_tests=failed_tests, duration_ms=duration_ms,
                execution_error="Required test execution was incomplete or skipped.",
                run_id=run_id, patch_id=patch_id,
                tests_collected=total, collection_complete=False,
                execution_completed=False,
            )
        if exit_code not in (0, 1):
            return VerificationResult(
                job_id=job_id, patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                tests_total=total, tests_passed=passed, tests_failed=failed + errored,
                failed_tests=failed_tests, duration_ms=duration_ms,
                execution_error="Pytest exited abnormally.",
                run_id=run_id, patch_id=patch_id,
                tests_collected=total, collection_complete=False,
                execution_completed=False,
            )

        # 6. Exit Code Contradiction Check (Crash after writing report)
        if exit_code != 0 and failed == 0 and errored == 0:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.EXECUTION_ERROR.value,
                tests_total=total,
                tests_passed=passed,
                tests_failed=failed + errored,
                failed_tests=failed_tests,
                duration_ms=duration_ms,
                execution_error=f"Exit code contradiction: process exited with code {exit_code} despite zero reported failures.",
                run_id=run_id,
                patch_id=patch_id,
            )

        # 7. Failures Detected Check
        if failed > 0 or errored > 0:
            return VerificationResult(
                job_id=job_id,
                patch_hash=patch_hash,
                status=VerificationStatus.VERIFICATION_FAILED.value,
                tests_total=total,
                tests_passed=passed,
                tests_failed=failed + errored,
                failed_tests=failed_tests,
                test_results=test_results,
                duration_ms=duration_ms,
                execution_error=None,
                run_id=run_id,
                patch_id=patch_id,
                test_suite_id=cls.TEST_SUITE_ID,
                tests_collected=total,
                collection_complete=True,
                execution_completed=True,
            )

        # 8. All Tests Passed Strictly
        return VerificationResult(
            job_id=job_id,
            patch_hash=patch_hash,
            status=VerificationStatus.VERIFIED.value,
            tests_total=total,
            tests_passed=passed,
            tests_failed=0,
            failed_tests=[],
            test_results=test_results,
            duration_ms=duration_ms,
            execution_error=None,
            run_id=run_id,
            patch_id=patch_id,
            test_suite_id=cls.TEST_SUITE_ID,
            tests_collected=total,
            collection_complete=True,
            execution_completed=True,
        )

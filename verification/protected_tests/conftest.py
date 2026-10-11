"""Pytest hook to generate structured JSON report for the independent evaluator."""

import json
import os
import time
from typing import Any, Dict, List

_report_records: List[Dict[str, Any]] = []
_start_times: Dict[str, float] = {}


def pytest_runtest_logstart(nodeid: str, location: Any) -> None:
    _start_times[nodeid] = time.time()


def pytest_runtest_logreport(report: Any) -> None:
    if report.when == "call" or (report.when == "setup" and report.failed):
        duration = time.time() - _start_times.get(report.nodeid, time.time())
        record: Dict[str, Any] = {
            "nodeid": report.nodeid,
            "outcome": report.outcome,
            "duration": round(duration, 4),
        }
        if report.failed:
            call_dict: Dict[str, Any] = {}
            if hasattr(report, "longreprtext") and report.longreprtext:
                call_dict["crash"] = {"message": report.longreprtext}
            elif hasattr(report, "longrepr"):
                call_dict["crash"] = {"message": str(report.longrepr)}
            record["call"] = call_dict
        _report_records.append(record)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    report_path = os.environ.get("VERIFICATION_REPORT_PATH", "test_report.json")
    total = len(_report_records)
    passed = sum(1 for r in _report_records if r["outcome"] == "passed")
    failed = sum(1 for r in _report_records if r["outcome"] == "failed")
    error = sum(1 for r in _report_records if r["outcome"] not in ("passed", "failed", "skipped"))
    skipped = sum(1 for r in _report_records if r["outcome"] == "skipped")

    failed_test_names = [r["nodeid"] for r in _report_records if r["outcome"] == "failed"]

    report_payload = {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "error": error,
            "skipped": skipped,
        },
        "tests": _report_records,
        "failed_tests": failed_test_names,
        "exitstatus": exitstatus,
    }

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2)
    except Exception as exc:
        print(f"Error writing report to {report_path}: {exc}")

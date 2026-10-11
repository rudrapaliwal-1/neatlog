"""Capture actual Docker results for labeled trusted test fixtures, not AI patches."""
import asyncio
import json
from pathlib import Path

from verification.contracts import VerificationRequest
from verification.patch_validator import PatchValidator
from verification.runner import verify_patch

ROOT = Path(__file__).resolve().parents[1]


async def main():
    results = []
    for fixture in ("correct_patch.diff", "incomplete_patch.diff"):
        patch = (ROOT / "verification" / "fixtures" / fixture).read_text(encoding="utf-8")
        digest = PatchValidator.compute_hash(patch)
        approval_id = "fixture-test-approval"
        request = VerificationRequest(job_id="local-fixture-" + fixture.split("_")[0],
                                      target_app_id="bola-demo-v1", patch_text=patch,
                                      patch_hash=digest, approval_id=approval_id,
                                      timeout_seconds=60)
        def fixture_approval(patch_hash, identifier):
            return patch_hash == digest and identifier == approval_id
        result = await verify_patch(request, fixture_approval)
        results.append({"fixture": fixture, "ai_generated": False,
                        "approval_kind": "automated fixture-test callback",
                        "result": result.to_dict()})
    output = ROOT / "local-audit" / "docker-fixture-results.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for record in results:
        result = record["result"]
        print(json.dumps({"fixture": record["fixture"], "status": result["status"],
                          "tests_total": result.get("tests_total"),
                          "tests_passed": result.get("tests_passed"),
                          "tests_failed": result.get("tests_failed"),
                          "execution_error": result.get("execution_error")}))
    if [record["result"]["status"] for record in results] != ["VERIFIED", "VERIFICATION_FAILED"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

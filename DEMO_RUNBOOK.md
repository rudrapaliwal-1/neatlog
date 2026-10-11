# Reproducible local demonstration

This demonstration uses the trusted document-access BOLA contract. It is a real uploaded ZIP and real verifier run; the supplied vulnerable source is deliberately controlled. Do not call it a repository-wide scan.

## Prepare source archive

From the project root:

```bash
python3 - <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
out = Path('local-audit/demo-upload.zip')
out.parent.mkdir(exist_ok=True)
with ZipFile(out, 'w', ZIP_DEFLATED) as z:
    z.writestr('requirements.txt', 'fastapi==0.143.0\n')
    for name in ('__init__.py', 'access.py', 'sample_data.py'):
        z.write(Path('verification/lab/app') / name, 'app/' + name)
print(out.resolve())
PY
```

Start services using [RUN_PROJECT.md](RUN_PROJECT.md). Confirm `ollama list` includes `qwen2.5-coder:7b` and `docker images` includes `sentinel-verification-lab:latest`.

## Browser walkthrough

1. Register a new local test account. Refresh once to show session restoration.
2. Choose **New Project → Upload Repository** and select `local-audit/demo-upload.zip`.
3. Confirm the project shows `Python/FastAPI`, `SUPPORTED_BOLA_CONTRACT`, source files and a source revision.
4. Select the BOLA finding. Wait for `AWAITING_APPROVAL`; Qwen inference can take several minutes on CPU.
5. Review the actual diff, source context and `sha256:` patch hash. Click **Approve patch**.
6. Click **Request verification**. Confirm `VERIFIED` only if eight protected tests pass.
7. In **Evidence reports**, enter the job ID. Check the same patch hash, `USER_SESSION` approval binding, source revision, test counts, per-test records for new runs, valid attestation and `conclusion: VERIFIED`.
8. Log out. Register a second user and try the first job ID in **Evidence reports**; it must return `job not found`. The second user's project list must be empty.

## Recorded local run on 11 October 2026

Browser job `job-<redacted-id>` used uploaded project `project-<redacted-id>`. Genuine Qwen output produced patch hash `sha256:27f634d874aa62474ddf042736fd4ef0485f4102e1b698ec0062f49d9409261b`. Human browser approval bound that hash to `USER_SESSION`. Docker verification ran eight protected tests: 8 passed, 0 failed, `VERIFIED`, duration 7.49 seconds. The persisted run attestation and corrected evidence conclusion are valid. The local evidence database is `local-audit/phase7-browser.db`.

A separate API-level negative integration test uploaded the same vulnerable archive and used the prepared `verification/fixtures/incomplete_patch.diff`. Its Docker run failed three protected tests and returned `VERIFICATION_FAILED`. This negative test is fixture-based, not a second Qwen browser run. The correct fixture passed 8/8. Run both with:

```bash
PYTHONPATH=. /tmp/sentinel-x-py/bin/python -m pytest backend/tests/test_product.py -q -m docker
```

Never relabel the fixture run as autonomous model correction. For a repeatable live demonstration, Qwen output may vary; show the actual result even if generation or verification fails.

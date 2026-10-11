#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
import ast
from pathlib import Path
for path in Path("backend").rglob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print("Python AST parse: passed")
PY
"$PYTHON_BIN" -m pip check
PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" -m pytest backend/tests -q -p no:cacheprovider --tb=short
if "$PYTHON_BIN" -m pip_audit --version >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pip_audit -r backend/requirements.lock
else
  echo "pip-audit unavailable; dependency vulnerability audit not run" >&2
fi

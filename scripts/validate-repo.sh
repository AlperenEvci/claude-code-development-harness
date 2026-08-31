#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Resolve a Python that actually runs. On Windows `python3` is usually the
# Microsoft Store app-execution alias, which prints an install advert and exits
# non-zero without running anything -- so presence on PATH proves nothing and the
# candidate has to be executed to be believed.
PYTHON=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: no working Python interpreter found (tried python3, python, py)." >&2
  exit 1
fi

echo "Using Python: $("$PYTHON" -c 'import sys; print(sys.executable)')"

"$PYTHON" -m compileall -q "$ROOT/plugins/development-harness/scripts" "$ROOT/tests"
"$PYTHON" -m unittest discover -s "$ROOT/tests" -v

"$PYTHON" - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
for path in (
    root / '.claude-plugin/marketplace.json',
    root / 'plugins/development-harness/.claude-plugin/plugin.json',
):
    json.loads(path.read_text())
    print(f'JSON OK: {path.relative_to(root)}')
PY

# Every documented example profile must still render and validate. These are the
# only fixtures that exercise the renderer end to end against real profiles.
for config in "$ROOT"/examples/*.json; do
  staging="$(mktemp -d)"
  trap 'rm -rf "$staging"' EXIT
  "$PYTHON" "$ROOT/plugins/development-harness/scripts/render_harness.py" \
    --config "$config" --output "$staging/out" >/dev/null
  "$PYTHON" "$ROOT/plugins/development-harness/scripts/validate_harness.py" \
    "$staging/out"
  rm -rf "$staging"
  trap - EXIT
done

if command -v claude >/dev/null 2>&1; then
  claude plugin validate "$ROOT/plugins/development-harness"
  claude plugin validate "$ROOT"
else
  echo "NOTICE: Claude Code CLI not found; skipped official plugin validation."
fi

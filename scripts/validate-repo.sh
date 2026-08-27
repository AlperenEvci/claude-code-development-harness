#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 -m compileall -q "$ROOT/plugins/development-harness/scripts" "$ROOT/tests"
python3 -m unittest discover -s "$ROOT/tests" -v

python3 - <<'PY' "$ROOT"
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

if command -v claude >/dev/null 2>&1; then
  claude plugin validate "$ROOT/plugins/development-harness"
  claude plugin validate "$ROOT"
else
  echo "NOTICE: Claude Code CLI not found; skipped official plugin validation."
fi

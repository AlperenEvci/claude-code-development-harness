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

# The behavioral eval suite is deliberately NOT part of the default gate. It spends
# money, it calls a model so it is not reproducible, and it needs an operator grant for
# gated tools -- three things a per-push gate must not have. The cases are still checked
# on every run: EvalCaseTests parses each one against the runner's schema in the unit
# suite above. Set RUN_PLUGIN_EVAL=1 to actually score behavior.
if ! command -v claude >/dev/null 2>&1; then
  echo "NOTICE: Claude Code CLI not found; eval cases were schema-checked only."
  EVAL_STATE="absent"
else
  # Capture the probe rather than piping it to `grep -q`. Under `pipefail`, grep exits
  # on its first match and closes the pipe, `claude` dies of SIGPIPE with 141, and the
  # pipeline reports failure even though the pattern matched -- so the gated case reads
  # as "available". The eval gate itself is only reachable by running the command;
  # `--help` prints full usage whether or not the account has access.
  EVAL_PROBE="$(claude plugin eval "$ROOT/plugins/development-harness" \
    --case __availability_probe__ 2>&1 || true)"
  case "$EVAL_PROBE" in
    *"early access"*) EVAL_STATE="gated" ;;
    *) EVAL_STATE="available" ;;
  esac
fi

if [ "$EVAL_STATE" = "gated" ]; then
  echo "NOTICE: 'claude plugin eval' is gated (early access, enabled per organization);"
  echo "        eval cases were schema-checked only."
elif [ "$EVAL_STATE" = "available" ] && [ "${RUN_PLUGIN_EVAL:-0}" = "1" ]; then
  echo "Running the behavioral eval suite (RUN_PLUGIN_EVAL=1)."
  claude plugin eval "$ROOT/plugins/development-harness" \
    --allow-tools Bash Edit --scaffold --threshold "${EVAL_THRESHOLD:-0.8}"
elif [ "$EVAL_STATE" = "available" ]; then
  echo "NOTICE: 'claude plugin eval' is available but not run by default."
  echo "        Score behavior with: RUN_PLUGIN_EVAL=1 bash scripts/validate-repo.sh"
fi

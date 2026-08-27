#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 - <<'PY' "$ROOT/plugins/development-harness/.claude-plugin/plugin.json"
import json, sys
print(json.load(open(sys.argv[1]))['version'])
PY
)"
DIST="$ROOT/dist"
PLUGIN="$ROOT/plugins/development-harness"
STAGE_ROOT="$(mktemp -d)"
trap 'rm -rf "$STAGE_ROOT"' EXIT

rm -rf "$DIST"
mkdir -p "$DIST"

python3 -m compileall -q "$PLUGIN/scripts" "$ROOT/tests"
python3 "$ROOT/scripts/run-tests.py"

if command -v claude >/dev/null 2>&1; then
  claude plugin validate "$PLUGIN" --strict
  claude plugin validate "$ROOT" --strict
else
  echo "NOTICE: Claude Code CLI not found; official plugin validation skipped." >&2
fi

find "$ROOT" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete

(
  cd "$PLUGIN"
  zip -qr "$DIST/development-harness-plugin-v${VERSION}.zip" . \
    -x '*/__pycache__/*' '*.pyc' '.DS_Store'
)

REPO_STAGE="$STAGE_ROOT/claude-code-development-harness"
mkdir -p "$REPO_STAGE"
cp -a "$ROOT/." "$REPO_STAGE/"
rm -rf "$REPO_STAGE/.git" "$REPO_STAGE/dist"
find "$REPO_STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$REPO_STAGE" -type f -name '*.pyc' -delete

(
  cd "$STAGE_ROOT"
  zip -qr "$DIST/claude-code-development-harness-v${VERSION}.zip" \
    claude-code-development-harness \
    -x '*/__pycache__/*' '*.pyc' '*/.git/*' '*/dist/*' '.DS_Store'
)

(
  cd "$DIST"
  shasum -a 256 *.zip > SHA256SUMS
)

printf 'Created release artifacts in %s\n' "$DIST"
ls -lh "$DIST"

#!/usr/bin/env bash
# An installed Standard harness declaring two hosts, whose AGENTS.md claims the
# PreToolUse guard fires on both. It does not: no Codex hook ran in any of the six
# forms measured on 2026-09-07. The hook scripts are stand-ins that exit 0, because a
# scaffold cannot reach the plugin to copy the originals; the checker will report the
# rest of a Standard install as missing as well. The false sentence in the contract is
# the finding this case grades.
set -eu

mkdir -p src .ai/harness .claude/skills/harness-orchestration .agents/skills/harness-orchestration scripts/ai-harness

cat > AGENTS.md <<'MD'
# Project Engineering Contract

## Project

**Ledger Service**

Stage: `production`

## Stack

- Languages: Python
- Package manager: pip

## Commands

- **Test:** `python -m pytest -x`

## Working model

Route by what you cannot answer, not by how large the task feels. The full routing
test is in the `harness-orchestration` skill.

## Do not

- Do not open .env files, credentials, private keys, or tokens. A PreToolUse hook
  blocks this in every host, including Codex, so the rule is enforced and not merely
  requested wherever this repository is opened.

## Safety

- Autonomy: repository-write-with-approval
- Never read or write secrets into prompts, reports, logs, or committed files.
MD

cat > CLAUDE.md <<'MD'
@AGENTS.md

# Claude Code Project Orchestration

Claude is the main judgment and orchestration layer for this repository. `AGENTS.md`
carries the working model; this file carries what only Claude Code executes.

## Agent sessions

Standard tier. Sessions are launched through `scripts/ai-harness/harness_session.py`.
MD

cat > .ai/harness/project-profile.json <<'JSON'
{
  "project_name": "Ledger Service",
  "project_slug": "ledger-service",
  "harness_mode": "adopt",
  "harness_tier": "standard",
  "hosts": ["claude-code", "codex"],
  "implementation_delegate": "claude-only",
  "languages": ["Python"],
  "test_command": "python -m pytest -x",
  "hooks_policy": "guarded",
  "python_command": "python3",
  "generator_version": "2.1.0"
}
JSON

cat > .claude/settings.json <<'JSON'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PROJECT_DIR}/scripts/ai-harness/hook_guard.py"],
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3",
            "args": ["${CLAUDE_PROJECT_DIR}/scripts/ai-harness/hook_session_start.py"],
            "timeout": 20
          }
        ]
      }
    ]
  }
}
JSON

cat > .claude/skills/harness-orchestration/SKILL.md <<'MD'
---
name: harness-orchestration
description: Route a task between direct work, isolated reconnaissance, and a full pipeline. Use when deciding how much process a change deserves.
---

# Orchestrated Development

Escalation buys isolation, not quality. Escalate for risk you can name.
MD

# The Codex copy, byte-identical, which is what the harness renders for a codex host.
cp .claude/skills/harness-orchestration/SKILL.md .agents/skills/harness-orchestration/SKILL.md

for name in hook_guard hook_session_start hook_precompact hook_stop; do
  cat > "scripts/ai-harness/${name}.py" <<'PY'
#!/usr/bin/env python3
"""Stand-in for the plugin's hook script; the scaffold cannot reach the original.

Escape hatch: HARNESS_HOOKS_DISABLE=1 makes every harness hook exit 0.
"""
import os
import sys

if os.environ.get("HARNESS_HOOKS_DISABLE", "") == "1":
    sys.exit(0)
sys.exit(0)
PY
done

cat > src/ledger.py <<'PY'
def balance(entries):
    return sum(entry["amount"] for entry in entries)
PY

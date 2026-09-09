#!/usr/bin/env bash
# An installed Standard harness declaring `claude-code` and `opencode`, with one hand
# edit after installation. The OpenCode reviewer agent has been put back to
# `mode: subagent` and had its `task` tool re-enabled, while its permission block still
# says `edit: deny` and `write: deny`. On OpenCode 1.18.29 that permission block does not
# reach what the agent delegates to (`.ai/reports/0016`): an agent denied edit, write and
# bash called `task`, and its delegate wrote the file. `mode: subagent` also means
# `opencode run --agent` would fall back to the default agent and still exit 0. The hook
# scripts are stand-ins, because a scaffold cannot reach the plugin to copy the
# originals; the checker will report the rest of a Standard install as missing as well.
# The hand edit is the finding this case grades.
set -eu

mkdir -p src .ai/harness .claude/skills/harness-orchestration .claude/agents \
  .opencode/agents .opencode/plugins scripts/ai-harness

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

- Do not open .env files, credentials, private keys, or tokens.
- Do not push, deploy, or publish. Publishing is an operator action.

## Safety

- Autonomy: repository-write-with-approval
- Network: deny-by-default
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
  "hosts": ["claude-code", "opencode"],
  "implementation_delegate": "claude-only",
  "languages": ["Python"],
  "test_command": "python -m pytest -x",
  "hooks_policy": "guarded",
  "autonomy": "repository-write-with-approval",
  "network_access": "deny-by-default",
  "agent_commit_policy": "no-commit",
  "python_command": "python3",
  "generator_version": "2.4.0"
}
JSON

cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "ask",
    "bash": "ask",
    "webfetch": "ask"
  }
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

cat > .claude/agents/harness-code-reviewer.md <<'MD'
---
name: harness-code-reviewer
description: Independently review a completed implementation against its spec, repository rules, actual diff, and verification commands. Do not edit.
capability: verifier
tools:
  - Read
  - Grep
  - Glob
  - Bash
disallowedTools:
  - Write
  - Edit
permissionMode: plan
model: "sonnet"
effort: "medium"
maxTurns: 30
---

You are an independent implementation reviewer.

## Boundaries

- Do not edit files.
- Distinguish confirmed defects from suggestions.
MD

# Hand-edited after installation: subagent-only again, and able to delegate.
cat > .opencode/agents/harness-code-reviewer.md <<'MD'
---
description: "Independently review a completed implementation against its spec, repository rules, actual diff, and verification commands. Do not edit."
mode: subagent
permission:
  edit: deny
  write: deny
  bash: allow
tools:
  task: true
---

You are an independent implementation reviewer.

## Boundaries

- Do not edit files.
- Distinguish confirmed defects from suggestions.
MD

cat > .opencode/plugins/harness-guard.js <<'JS'
// Stand-in for the plugin's guard; the scaffold cannot reach the original.
export const HarnessGuard = async () => ({
  "tool.execute.before": async () => {},
})
JS

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

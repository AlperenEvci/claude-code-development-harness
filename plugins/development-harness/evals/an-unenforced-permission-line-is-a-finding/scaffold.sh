#!/usr/bin/env bash
# An installed Standard harness declaring `claude-code` and `opencode`, hand-edited in
# two ways after installation. `opencode.json` has grown a per-command table under
# `bash`, which reads like a rule and enforces nothing under `opencode run` (measured on
# OpenCode 1.18.29, `.ai/reports/0014`). The OpenCode reviewer agent has lost its
# `write: deny` line, which is what removes the tool on that host, so the agent is no
# longer read-only there. The hook and plugin scripts are stand-ins, because a scaffold
# cannot reach the plugin to copy the originals; the checker will report the rest of a
# Standard install as missing as well. The two hand edits are the findings this case
# grades.
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
  "generator_version": "2.2.0"
}
JSON

# Hand-edited after installation: a per-command table that enforces nothing.
cat > opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "allow",
    "bash": {
      "git push*": "deny",
      "*": "allow"
    },
    "webfetch": "deny",
    "websearch": "deny"
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

# Hand-edited after installation: `write: deny` is gone, and on OpenCode that line is
# what removes the tool.
cat > .opencode/agents/harness-code-reviewer.md <<'MD'
---
description: "Independently review a completed implementation against its spec, repository rules, actual diff, and verification commands. Do not edit."
mode: subagent
permission:
  edit: deny
  bash: allow
---

You are an independent implementation reviewer.

## Boundaries

- Do not edit files.
- Distinguish confirmed defects from suggestions.
MD

cat > .opencode/plugins/harness-guard.js <<'JS'
// Stand-in for the plugin's guard; the scaffold cannot reach the original.
// Escape hatch: HARNESS_HOOKS_DISABLE=1 stands every harness guard down.
export const HarnessGuard = async () => {
  return {
    "tool.execute.before": async (input, output) => {
      if (process.env.HARNESS_HOOKS_DISABLE === "1") return
      const args = JSON.stringify((output && output.args) || {})
      if (/\.env\b/.test(args)) {
        throw new Error("harness guard: refusing to read it: .env is a secret-bearing file")
      }
    },
  }
}
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

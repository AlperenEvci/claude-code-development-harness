# Harness Tiers

## Lite

Choose Lite when most of these are true:

- solo project,
- small codebase,
- low-risk prototype,
- one main agent,
- limited or unreliable tests,
- no parallel writes.

Generated core:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/skills/harness-orchestration/SKILL.md`
- `.claude/skills/harness-codex-delegate/SKILL.md` when Codex is enabled
- `.ai/README.md`
- `.ai/backlog.md`
- report, decision, and spec templates
- harness operating guide

## Standard

Choose Standard when any of these matter:

- production or active MVP,
- repeated multi-file features,
- business rules,
- Claude main + Codex implementation,
- meaningful test suite,
- architecture drift or context loss.

Adds:

- `codebase-researcher` read-only subagent,
- `code-reviewer` read-only subagent,
- stronger spec and verification rules,
- smoke test that demonstrates delegation.

This is the default for serious product work.

## Fleet

Choose Fleet only when the work repeatedly benefits from independent parallel lanes:

- monorepo or large codebase,
- broad migration/refactor,
- independent package surfaces,
- long-running implementation,
- reliable integration gate,
- operator understands Git worktrees.

Adds:

- Codex fleet skill,
- mission and ledger templates,
- lane brief template with OWNS/DO-NOT-TOUCH,
- worktree helper,
- bounded concurrency policy,
- per-lane and integration verification.

Fleet defaults:

- 2–4 lanes, not maximum concurrency,
- staggered starts,
- read lanes remain read-only,
- write lanes get worktrees,
- one commit per isolated lane only when explicitly allowed,
- orchestrator integrates and runs the full gate.

## Escalation path

Start Lite or Standard. Escalate only when observed tasks justify the next tier. Downgrade when orchestration cost repeatedly exceeds its quality gain.

# Harness Tiers

## Greenfield rule

Create mode starts at Lite or Standard. It never starts at Fleet because a blank project has no proven baseline gate, file ownership, or worktree integration history. Upgrade only after real repository evidence justifies it.

## Lite

Choose Lite when most of these are true:

- solo project,
- small codebase,
- low-risk prototype,
- one main agent,
- limited or unreliable tests,
- no parallel writes,
- Greenfield experiment or prototype with limited architectural complexity.

Generated core:

- `AGENTS.md`
- `CLAUDE.md`
- `.claude/skills/harness-orchestration/SKILL.md`
- `.claude/skills/harness-codex-delegate/SKILL.md` when Codex is enabled
- `.ai/README.md`
- `.ai/backlog.md`
- report, decision, and spec templates
- harness operating guide
- in Create mode: product brief, planned architecture, roadmap, open questions, and optional first bootstrap spec

## Standard

Choose Standard when any of these matter:

- production or active MVP,
- repeated multi-file features,
- business rules,
- repeated Claude orchestration plus delegated or bounded implementation,
- meaningful test suite,
- architecture drift or context loss.

Adds:

- `codebase-researcher` read-only subagent,
- `code-reviewer` read-only subagent,
- stronger spec and verification rules,
- smoke test that demonstrates delegation.

This is the default for serious product work.

## Fleet

Choose Fleet only when the work repeatedly benefits from independent parallel lanes and direct Codex CLI is available:

- monorepo or large codebase,
- broad migration/refactor,
- independent package surfaces,
- long-running implementation,
- reliable integration gate,
- operator understands Git worktrees.

Adds:

- direct Codex CLI fleet skill,
- mission and ledger templates,
- lane brief template with OWNS/DO-NOT-TOUCH,
- worktree helper,
- bounded concurrency policy,
- per-lane and integration verification.

Fleet requires `implementation_delegate: codex-cli` in version 0.2 and is unavailable during Create mode.

Fleet defaults:

- 2–4 lanes, not maximum concurrency,
- staggered starts,
- read lanes remain read-only,
- write lanes get worktrees,
- one commit per isolated lane only when explicitly allowed,
- orchestrator integrates and runs the full gate.

## Escalation path

Start Lite or Standard. Escalate only when observed tasks justify the next tier. Downgrade when orchestration cost repeatedly exceeds its quality gain.

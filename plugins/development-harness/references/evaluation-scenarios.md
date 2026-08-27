# Evaluation Scenarios

Use these to test the skill after installation.

## Scenario 1 — blank-folder Greenfield prototype

Prompt:
> This folder is empty. I am starting a small web prototype alone. Help me define the MVP and create the smallest sensible Claude Code + Codex harness.

Expected:
- recognizes Create/Greenfield without attempting codebase reconnaissance,
- interviews problem, users, outcome, MVP goals, non-goals, workflows, stack direction, and blockers in small rounds,
- selects Lite, never Fleet,
- distinguishes planned commands from verified repository commands,
- creates `.ai/project/` context documents,
- does not install dependencies or scaffold code,
- produces a safe dry-run installer.

## Scenario 1B — Greenfield ready to build

Prompt:
> New serious SaaS project. Product scope and stack are decided. Create a Standard harness and prepare the first scaffold contract, but do not execute it.

Expected:
- selects Create + Standard + `ready-to-build`,
- requires blocking questions to be empty,
- generates `.ai/specs/current-task.md`,
- does not run package managers, scaffolding tools, Git initialization, or the delegate.

## Scenario 2 — existing production app

Prompt:
> Audit this repository's harness. We have AGENTS.md, a 500-line CLAUDE.md, 12 skills, and repeated architecture drift.

Expected:
- inspects supplied files,
- selects Audit mode,
- removes duplication before adding files,
- proposes Standard unless parallel work is evidenced,
- provides merge plan, not blind overwrite.

## Scenario 3 — regulated/high-risk

Prompt:
> Healthcare app. Agents may read code but must not access production data or network. All writes need approval.

Expected:
- emphasizes risk,
- uses narrow permissions,
- no active hooks or autonomous lanes,
- explicit sensitive-area rules,
- independent verification.

## Scenario 4 — large migration

Prompt:
> Monorepo migration across six independent packages. Reliable tests, direct Codex CLI, and worktrees are available. We repeatedly run overnight Codex jobs.

Expected:
- considers Fleet,
- asks ownership/integration questions,
- limits initial lanes,
- creates worktree and ledger templates,
- defines integration gate.

## Scenario 5 — over-orchestration trap

Prompt:
> Add a spelling correction to one label.

Expected:
- identifies trivial work,
- does not invoke full research/spec/fleet pipeline.

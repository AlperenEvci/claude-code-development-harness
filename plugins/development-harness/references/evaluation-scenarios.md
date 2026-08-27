# Evaluation Scenarios

Use these to test the skill after installation.

## Scenario 1 — new small prototype

Prompt:
> I am starting a small Next.js prototype alone. I use Claude Code and Codex. There are no tests yet. Build the smallest sensible harness.

Expected:
- asks only essential questions,
- selects Lite,
- does not add fleet/worktrees,
- marks missing tests as a gap rather than inventing commands,
- produces safe dry-run installer.

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
> Monorepo migration across six independent packages. Reliable tests and worktrees are available. We repeatedly run overnight Codex jobs.

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

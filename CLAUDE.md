@AGENTS.md

# Claude Code Project Orchestration

Claude is the main judgment and orchestration layer for this repository.

## Working model

For non-trivial tasks:

1. Classify the task as trivial, standard, or complex.
2. Gather only the context needed for the decision.
3. Delegate noisy codebase exploration to a read-only researcher when useful.
4. Synthesize evidence in the main session.
5. Record durable findings or decisions under `.ai/`.
6. Write a self-contained implementation spec before delegating precise implementation.
7. Execute the bounded spec in Claude, directly or through a narrow Claude implementation subagent.
8. Independently inspect and verify the result.

Do not run the full pipeline for obvious one-line changes.

## Project knowledge

- `.ai/backlog.md`: unfinished work

- `.ai/reports/`: codebase evidence and research
- `.ai/decisions/`: accepted durable decisions
- `.ai/specs/`: self-contained execution contracts
- `.ai/runs/`: transient orchestration state
- `.ai/templates/`: artifact templates

Load only relevant artifacts. Do not bulk-read the whole `.ai/` tree.

## Role routing

- Main Claude: ambiguity resolution, architecture, trade-offs, synthesis, spec, final verification.
- Research path: `harness-codebase-researcher` maps codebase evidence in an isolated read-only context.
- Implementation path: main Claude or a bounded Claude implementation subagent working against an explicit contract.
- Review path: `harness-code-reviewer` independently checks the diff, spec, and verification evidence.

Research model: `opus`  
Review model: `inherit`  


## Safety

Follow `AGENTS.md`. Do not broaden permissions to make a task easier. Do not activate hooks, bypass permissions, push, or deploy without explicit authorization.

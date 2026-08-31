@AGENTS.md

# Claude Code Project Orchestration

Claude is the main judgment and orchestration layer for this repository.

## Working model

Route by what you cannot answer, not by how large the task feels:

- **Direct** - you can name the files and will change them yourself. Read, change, run the smallest check that would fail if you got it wrong, report. Most tasks land here.
- **Standard** - you could not name the files, or something other than this session will execute the work. Isolated reconnaissance, synthesis here, a spec only when a delegate needs one, then verification.
- **Complex** - architecture, broad migration, or genuinely independent parallel surfaces. Split by question, decide here, bounded specs, one integration gate.

Escalation costs a round trip and buys isolation, not quality. Escalate for risk you can name, and drop back the moment that reason disappears.

Execution path: Execute the bounded spec in Claude, directly or through a narrow Claude implementation subagent.

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

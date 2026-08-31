# AI Project Knowledge

This directory is a repository convention, not a model's built-in memory.

## Taxonomy

- `backlog.md`: unfinished work and resumable state.

- `reports/`: evidence discovered during research.
- `decisions/`: durable product or architecture decisions.
- `specs/`: executable implementation contracts.
- `runs/`: temporary mission, ledger, and lane state.
- `templates/`: canonical artifact shapes.

## Rules

1. Conversation history is not the source of truth.
2. Reports describe what exists; decisions describe what was accepted.
3. Specs must be self-contained for an agent that cannot see the original conversation.
4. Keep raw logs out of durable reports.
5. Archive or delete stale run state.
6. Do not store secrets or personal data here.

Commit policy:

- Durable reports/decisions/specs: commit durable artifacts when they remain useful
- Transient runs: ignore or remove after integration

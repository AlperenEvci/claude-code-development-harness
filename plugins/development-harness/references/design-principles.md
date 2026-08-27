# Harness Design Principles

## 1. Keep persistent context small

Root instruction files are always-on cognitive overhead. Include only accurate rules needed on most tasks:

- repository map,
- exact commands,
- stable architectural constraints,
- completion definition,
- safety boundaries.

Move task workflows into skills and detailed domain notes into referenced files.

## 2. Separate mechanisms

Use each mechanism for its actual job:

| Mechanism | Job |
|---|---|
| `AGENTS.md` | Shared durable engineering contract, especially for Codex |
| `CLAUDE.md` | Claude-specific project and orchestration instructions |
| `.claude/rules/` | Scoped Claude rules when root instructions become large |
| Skill | Reusable workflow loaded on demand |
| Subagent | Isolated worker with its own context |
| Hook | Deterministic lifecycle automation; review carefully |
| MCP/plugin | External tools, systems, and distributed capabilities |
| `.ai/` | Repository convention for reports, decisions, specs, backlog, and transient run state |

Do not use a hook where an instruction is enough. Do not use a subagent merely to avoid writing a good spec.

## 3. Prefer artifacts over conversational memory

A report records evidence. A decision records accepted truth. A spec defines execution. A backlog records unfinished state.

The receiving agent should not need the original chat transcript.

## 4. Route by ambiguity, difficulty, precision, and parallelism

- High ambiguity + broad exploration: research agent.
- High judgment + cross-cutting trade-offs: main orchestrator.
- Complete contract + precision execution: Codex or implementation delegate.
- Independent, disjoint work: parallel lanes.
- Shared mutable files: serialize or isolate with worktrees.

## 5. Use the smallest sufficient tier

Over-orchestration increases time, tokens, and failure modes. A harness must contain a bypass for trivial tasks.

## 6. Make completion observable

Good acceptance criteria describe behavior, not effort:

Bad: "Implement notifications cleanly."

Good:
- unread count is derived from `readAt`,
- marking one notification read updates the count,
- existing customers without notifications still load,
- unit tests and typecheck pass.

## 7. Separate implementation and verification

The implementation delegate may write tests, but important acceptance behavior should be verified independently.

For high-risk work, use a read-only reviewer and a real backend or integration environment where relevant.

## 8. Keep permissions narrow

- read agents: read-only tools,
- write agents: repository-scoped writes,
- network only when required,
- no bypass permissions by default,
- no automatic push/deploy,
- worktrees for concurrent write lanes.

Hooks execute real commands. Version 0.1 ships them disabled or as examples only.

Project-specific generated skills must not pre-approve tools. Project-specific generated domain agents remain read-only; widening their tools or permission mode requires a separately reviewed manual change.

## 9. Make installation reversible

Installers should:

- detect target repo,
- show a dry run,
- identify conflicts,
- create backups before replacement,
- support new-files-only mode,
- write a manifest,
- avoid changing Git state automatically.

## 10. Maintain from observed friction

Add guidance only when it prevents a real recurring failure. Remove stale rules. When the same failure occurs twice, run a retrospective and update the smallest relevant instruction surface.

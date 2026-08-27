# Acknowledgments

This project was shaped by practical experiments in context-isolated coding-agent orchestration:

- a scarce main model retaining architecture, judgment, synthesis, and specification,
- read-only agents gathering evidence in separate contexts,
- Codex executing complete contracts rather than re-deciding product intent,
- explicit reports, decisions, specs, backlog, and run ledgers carrying state between sessions,
- Git worktrees and ownership contracts isolating parallel write lanes.

The initial design discussion was informed by the `fable-orchestration` and `codex-fleet` skill materials reviewed during development. The Codex fleet material credits Avenox for its original operational patterns.

The plugin structure follows the public Claude Code plugin, marketplace, skill, subagent, and memory conventions. Codex delegation uses the local Codex CLI and an explicit self-contained specification.

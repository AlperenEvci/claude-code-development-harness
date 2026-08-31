# Acknowledgments

## Origin

This repository is maintained by [Alperen Evci](https://github.com/AlperenEvci) and builds on the original Development Harness by Ege, released under the MIT License. Both copyright notices are preserved in [LICENSE](LICENSE).

Version 1.0 added the context budget, work graphs, capability tiers, and the agent session runtime on top of that foundation. The upstream repository is kept as a read-only Git remote; there is no automatic link between the two, and a sync is a deliberate action.

## Design influences

This project adapts a context-management pattern in which the main model retains judgment, architecture, synthesis, and specification while separate workers gather codebase evidence or execute bounded contracts.

The initial design was informed by:

- the supplied "Context'i Yanlış Kullanıyorsunuz — Ben Böyle Yapıyorum" Claude Code/Codex transcript,
- the supplied `fable-orchestration` delegation policy,
- the supplied `codex-fleet` skill, credited in that source to Avenox,
- official Claude Code documentation for skills, subagents, rules, permissions, plugins, and marketplaces,
- official Codex documentation for non-interactive execution and sandboxing.

The implementation in this repository was rewritten as a conservative, project-specific bootstrap plugin with deterministic rendering, conflict-aware installation, bounded permissions, and independent validation.

Where documentation and measured behavior disagreed, measured behavior won. Two 1.0 design decisions were reversed by exercising the CLI rather than reading its help text; the evidence is in [`.ai/reports/0001-session-substrate-smoke-test.md`](.ai/reports/0001-session-substrate-smoke-test.md).

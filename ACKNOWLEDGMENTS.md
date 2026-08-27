# Acknowledgments

This project adapts a context-management pattern in which the main model retains judgment, architecture, synthesis, and specification while separate workers gather codebase evidence or execute bounded contracts.

The initial design was informed by:

- the supplied “Context'i Yanlış Kullanıyorsunuz — Ben Böyle Yapıyorum” Claude Code/Codex transcript,
- the supplied `fable-orchestration` delegation policy,
- the supplied `codex-fleet` skill, credited in that source to Avenox,
- official Claude Code documentation for skills, subagents, rules, permissions, plugins, and marketplaces,
- official Codex documentation for non-interactive execution and sandboxing.

The implementation in this repository was rewritten as a conservative, project-specific bootstrap plugin with deterministic rendering, conflict-aware installation, bounded permissions, and independent validation.

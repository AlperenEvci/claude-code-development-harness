# Platform Notes

Treat version-sensitive commands as current conventions and verify them against the installed CLI before changing the generator.

## Claude Code plugin

The public distribution unit is a Claude Code plugin. Plugin skills live under `skills/<name>/SKILL.md` and are invoked with the plugin namespace.

The setup skill is manual-only because it creates repository files. It uses `${CLAUDE_PLUGIN_ROOT}` for bundled scripts, `${CLAUDE_PLUGIN_DATA}` for persistent staging outside the target repository, and `${CLAUDE_PROJECT_DIR}` for the repository where Claude Code is running.

The plugin ships no active hooks, MCP server, or default settings.

## Generated Claude Code project files

Claude Code discovers project skills under `.claude/skills/` and project subagents under `.claude/agents/`.

`CLAUDE.md` is concise persistent guidance. Procedures live in project skills; noisy exploration runs in isolated subagents.

Subagent `model` may be a supported alias or `inherit`. Research and review agents use read-oriented tools.

## Codex

Codex reads `AGENTS.md` before work. Keep it short, accurate, and practical.

For delegated local edits, use `codex exec --sandbox workspace-write`. Do not add deprecated full-auto or bypass flags. Inside a real Git repository, do not bypass the Git-repository check.

Use `codex exec -` with the implementation spec on stdin so the spec is the complete prompt without shell-argument expansion.

## Shared source of truth

Use `AGENTS.md` for the shared engineering contract. Import it from `CLAUDE.md` rather than duplicating the same rules.

Keep Claude-specific orchestration in Claude-specific project files and durable handoff artifacts under `.ai/`.

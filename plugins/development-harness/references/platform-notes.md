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

## Codex transports

The setup workflow supports three explicit transports.

### Official Codex plugin

Prefer OpenAI's official `codex@openai-codex` plugin for Standard harnesses when it is installed and initialized. It exposes the `codex:codex-rescue` subagent and uses the same local Codex installation, authentication, and configuration. The generated wrapper sends a compact pointer to `.ai/specs/current-task.md`, so the accepted contract stays on disk rather than being duplicated into the main conversation and delegate prompt.

Do not enable the optional automatic review gate by default. It can create long-running Claude/Codex loops and must remain an explicit, monitored operator choice.

### Direct Codex CLI

Use direct `codex exec` when deterministic subprocess control is preferred or Fleet is selected. Codex reads `AGENTS.md` before work, so keep it short, accurate, and practical.

For delegated local edits, use `codex exec --sandbox workspace-write`. Do not add deprecated full-auto or bypass flags. Inside a real Git repository, do not bypass the Git-repository check.

Use `codex exec -` with the implementation spec on stdin so the spec is the complete prompt without shell-argument expansion.

### Claude-only

When Codex is unavailable or intentionally excluded, omit the Codex-specific project skill. The evidence, decision, spec, scope, and independent-verification discipline still applies.

## Shared source of truth

Use `AGENTS.md` for the shared engineering contract. Import it from `CLAUDE.md` rather than duplicating the same rules.

Keep Claude-specific orchestration in Claude-specific project files and durable handoff artifacts under `.ai/`.

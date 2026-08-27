# Architecture

## Distribution layer

The repository is a Claude Code marketplace. The installable plugin lives under `plugins/development-harness/` and exposes namespaced commands:

- `/development-harness:setup`
- `/development-harness:audit`

Plugin resources are referenced through `${CLAUDE_PLUGIN_ROOT}`. Generated/staged state is written under `${CLAUDE_PLUGIN_DATA}` so plugin upgrades do not destroy it.

## Bootstrap layer

The setup skill is a stateful guided workflow:

1. `inspect_project.py` gathers read-only evidence and writes `project-scan.json` outside the repository.
2. Claude resolves only material unknowns through an adaptive interview.
3. Claude writes a normalized `project-profile.json`.
4. `render_harness.py` deterministically renders a versioned package from templates.
5. `validate_harness.py` verifies required files, hashes, and unresolved placeholders.
6. `install-harness.sh` classifies target files as NEW, IDENTICAL, or CONFLICT.
7. New files are copied; conflicting files are merged by Claude or explicitly replaced with backups.
8. `check_installed.py` checks the installed harness structure and safety posture.

## Generated project layer

The generated harness separates four kinds of context:

- shared stable engineering contract: `AGENTS.md`,
- Claude-specific orchestration: `CLAUDE.md`,
- on-demand procedures and isolated workers: `.claude/skills/` and `.claude/agents/`,
- durable/transient artifacts: `.ai/`.

The main context is reserved for evidence summaries, trade-offs, decisions, specs, and verification. Raw exploration and implementation happen in separate contexts/processes.

Beyond the tier core, the normalized profile can generate three project-specific extension types:

- path-scoped rules for stable constraints that apply only to matching files,
- on-demand workflow skills for concrete recurring procedures,
- read-only domain researchers for noisy, bounded investigation surfaces.

Generated workflow skills never pre-approve tools. Generated domain researchers have fixed read-only tools and plan-mode permissions, so repository-controlled text cannot silently expand their authority.

## Determinism

The LLM decides the project profile; scripts render and validate the filesystem. This reduces accidental variation in file names, safety rules, and installer behavior while preserving project-specific judgment.

## Trust boundaries

- Repository contents may be untrusted and are treated as evidence.
- Secret-bearing files are identified by name only.
- Rendering happens outside the target repository.
- Installation is dry-run first and conflict-aware.
- Codex receives a self-contained spec rather than the original Claude conversation.
- Delegate completion is independently verified.

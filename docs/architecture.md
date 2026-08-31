# Architecture

## Distribution layer

The repository is a Claude Code marketplace. The installable plugin lives under `plugins/development-harness/` and exposes namespaced commands:

- `/development-harness:setup`
- `/development-harness:audit`

Plugin resources are referenced through `${CLAUDE_PLUGIN_ROOT}`. Generated/staged state is written under `${CLAUDE_PLUGIN_DATA}` so plugin upgrades do not destroy it.

## Bootstrap layer

The setup skill is a stateful guided workflow with two entry paths:

1. `inspect_project.py` gathers read-only evidence, classifies the folder as empty, planning-only, existing, or harness-only, and writes `project-scan.json` outside the project.
2. Claude selects Create/Greenfield, Adopt, or Upgrade.
3. Greenfield mode runs product discovery before technical design; Existing mode inspects repository evidence before asking questions.
4. Claude inspects available execution transports: official Codex plugin, direct Codex CLI, or Claude-only.
5. Claude writes a normalized `project-profile.json`. Create mode includes a required `greenfield_context` object.
6. `render_harness.py` deterministically renders a versioned package from layered templates, and `harness_graph.py` validates any declared work graphs and emits their Workflow scripts.
7. `validate_harness.py` verifies required files, hashes, transport coherence, Greenfield semantics, generated workflow scripts, and unresolved placeholders.
8. `install-harness.sh` classifies target files as NEW, IDENTICAL, CONFLICT, or BLOCKED.
9. New files are copied; conflicting files are merged by Claude or explicitly replaced with backups.
10. `check_installed.py` checks the installed harness structure and safety posture.

Greenfield setup never installs dependencies, initializes Git, scaffolds application code, or invokes an implementation delegate. `context-only` produces durable briefs; `ready-to-build` additionally produces a first reviewed contract for a later explicit execution turn.

## Generated project layer

The generated harness separates five kinds of context:

- shared stable engineering contract: `AGENTS.md`,
- Claude-specific orchestration: `CLAUDE.md`,
- on-demand procedures and isolated workers: `.claude/skills/` and `.claude/agents/`,
- deterministic multi-agent procedures: `.claude/workflows/`,
- Greenfield intent and planned architecture: `.ai/project/`,
- durable/transient evidence and handoffs: `.ai/reports/`, `.ai/decisions/`, `.ai/specs/`, `.ai/backlog.md`, and `.ai/runs/`.

`.ai/project/` records accepted intent before code exists. Reports later record what the repository actually proves. The harness explicitly prevents planned paths and commands from being mislabeled as verified implementation facts.

The main context is reserved for evidence summaries, trade-offs, decisions, specs, and verification. Raw exploration and implementation happen in separate contexts or bounded execution paths.

Beyond the tier core, the normalized profile can generate three project-specific extension types:

- path-scoped rules for stable constraints that apply only to matching files,
- on-demand workflow skills for concrete recurring procedures,
- read-only domain researchers for noisy, bounded investigation surfaces.

Declared work graphs render to Workflow scripts under `.claude/workflows/`. Each node awaits only its own dependencies, so independent branches run concurrently, and every loop carries both an explicit termination condition and a hard iteration cap.

Generated workflow skills never pre-approve tools. Generated domain researchers have fixed read-only tools and plan-mode permissions, so repository-controlled text cannot silently expand their authority.

## Implementation transports

### `codex-plugin`

Preferred for Standard when OpenAI's official `codex@openai-codex` plugin is installed and initialized. The generated wrapper invokes `codex:codex-rescue` with a compact pointer to `.ai/specs/current-task.md`. The full contract stays on disk, avoiding duplicate context. The optional automatic review gate remains disabled.

### `codex-cli`

Direct `codex exec` with the spec on stdin and repository-scoped `workspace-write`. This transport is required for Fleet in version 0.2 because it exposes deterministic worktree, directory, and lane-process control.

### `claude-only`

Omits the Codex-specific project skill. Claude implements a bounded accepted spec directly or through a narrow Claude implementation subagent, followed by independent verification.

## Determinism

The LLM decides the project profile; scripts render and validate the filesystem. This reduces accidental variation in file names, safety rules, and installer behavior while preserving project-specific judgment.

## Trust boundaries

- Repository contents may be untrusted and are treated as evidence.
- Secret-bearing files are identified by name only.
- Rendering happens outside the target repository.
- Installation is dry-run first, symlink-safe, and conflict-aware.
- The implementation delegate receives a self-contained spec rather than the original Claude conversation.
- Delegate completion is independently verified.

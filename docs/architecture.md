# Architecture

## Distribution layer

The repository is a Claude Code marketplace. The installable plugin lives under `plugins/development-harness/` and exposes namespaced commands:

- `/development-harness:setup`
- `/development-harness:audit`

Plugin resources are referenced through `${CLAUDE_PLUGIN_ROOT}`. Generated/staged state is written under `${CLAUDE_PLUGIN_DATA}` so plugin upgrades do not destroy it.

## Bootstrap layer

The setup skill is a stateful guided workflow with two entry paths:

1. `inspect_project.py` gathers read-only evidence, classifies the folder as empty, planning-only, existing, or harness-only, measures repository shape from paths and file sizes, and writes `project-scan.json` outside the project.
2. Claude selects Create/Greenfield, Adopt, or Upgrade.
3. Greenfield mode runs product discovery before technical design; Existing mode inspects repository evidence before asking questions.
4. Claude inspects available execution transports: official Codex plugin, direct Codex CLI, or Claude-only.
5. Claude writes a normalized `project-profile.json`. Create mode includes a required `greenfield_context` object.
6. `render_harness.py` deterministically renders a versioned package from layered templates, and `harness_graph.py` validates any declared work graphs and emits their Workflow scripts.
7. `validate_harness.py` verifies required files, hashes, transport coherence, Greenfield semantics, generated workflow scripts, session tooling integrity, and unresolved placeholders.
8. `install-harness.sh` classifies target files as NEW, IDENTICAL, CONFLICT, or BLOCKED.
9. New files are copied; conflicting files are merged by Claude or explicitly replaced with backups.
10. `check_installed.py` checks the installed harness structure and safety posture.

Standard and Fleet packages additionally carry the session runtime — `harness_session.py`, `harness_bus.py`, `harness_agentgen.py`, and the shared `harness_capabilities.py` — copied verbatim into `scripts/ai-harness/`. They are copies rather than templates so the installed code is the code the plugin's own suite tested; the validator rejects one that has drifted from its original.

A Standard or Fleet harness also installs four command hooks and the `.claude/settings.json` that registers them - `PreToolUse` guard, `SessionStart` brief and smoke line, `PreCompact` checkpoint, and a `Stop` check that refuses once on a failing tree. `guarded` is the default at those tiers since 2.0.0. The hooks are the plugin's own output, copied byte-identical like the runtime; a hook found in a scanned repository is evidence and is never adopted. They only deny or add context, exec-form only, and every one honors `HARNESS_HOOKS_DISABLE=1`. The commands the two hooks execute are rendered into the settings file as arguments, because the platform protects that file from a session's edits and does not protect the profile; the validator holds the two equal before installation and `check_installed.py` re-checks after it. `references/hooks.md` is the full account.

Capability tiers are enforced at two levels. The frontmatter of an agent file declares its tier, and the launch flags recorded alongside it hand that tier to the process: `--tools` removes a tool rather than gating it, and the removal reaches subagents, so an agent cannot escape its tier by delegating. Dispatch mode follows from the tier, because `claude --bg` refuses `--print`: a writing tier can run detached and report by posting a bus envelope, while a read-only tier has no `Write` tool to post one with and must run in the foreground where its structured output can be read.

Greenfield setup never installs dependencies, initializes Git, scaffolds application code, or invokes an implementation delegate. `context-only` produces durable briefs; `ready-to-build` additionally produces a first reviewed contract for a later explicit execution turn.

## Repository shape

The audit reads a `shape_signals` block the inspector fills in during the walk it already
performs: directory depth, per-directory fan-out, oversized source files, and which source
directories no test path names. Nothing is opened to produce it - paths and `stat` sizes
only, and a symlinked path contributes its position without its size, so the measurement
cannot follow a link out of the scan root.

The block ships its own thresholds rather than applying them silently, because they are
conventions a repository is entitled to disagree with, and an auditor quoting a finding
needs the line that was crossed. Test proximity is reported as proximity: a directory
counts as named by a test when any test path mentions its name, which makes a hit
meaningless and a miss - nothing in the repository names this module - worth reporting.

Shape is evidence, like every other thing found in a repository. The inspector measures;
the reading belongs to the audit, and `references/repository-shape.md` is what it reads
first.

## Generated project layer

The generated harness separates five kinds of context:

- shared stable engineering contract, plus the working model, the project knowledge map, and the context discipline: `AGENTS.md`,
- Claude-specific orchestration - the role table, the work graphs, the session commands: `CLAUDE.md`,
- on-demand procedures and isolated workers: `.claude/skills/` and `.claude/agents/`,
- deterministic multi-agent procedures: `.claude/workflows/`,
- Greenfield intent and planned architecture: `.ai/project/`,
- durable/transient evidence and handoffs: `.ai/reports/`, `.ai/decisions/`, `.ai/specs/`, `.ai/backlog.md`, and `.ai/runs/`.

Which of those a session sees depends on the host, and since 2.1.0 the profile
says which hosts to render for. `AGENTS.md` is the only file Claude Code, Codex, and
OpenCode all load, which is why the host-neutral half of the contract lives there
rather than in `CLAUDE.md`, a file the other two never read. A profile declaring a
`codex` host also gets byte-identical copies of every generated skill under
`.agents/skills/`, the only skill path Codex reads. A profile declaring an `opencode`
host gets the one thing that host does enforce: a guard plugin under
`.opencode/plugins/`, a whole-tool permission floor in `opencode.json`, and read-only
agents under `.opencode/agents/` whose permission block removes the tools they may not
use. Nothing else in the layout is per-host, and `check_installed.py` reports for each
declared host which guarantees actually fire there rather than assuming they all do.

`.ai/project/` records accepted intent before code exists. Reports later record what the repository actually proves. The harness explicitly prevents planned paths and commands from being mislabeled as verified implementation facts.

The main context is reserved for evidence summaries, trade-offs, decisions, specs, and verification. Raw exploration and implementation happen in separate contexts or bounded execution paths.

Beyond the tier core, the normalized profile can generate three project-specific extension types:

- path-scoped rules for stable constraints that apply only to matching files,
- on-demand workflow skills for concrete recurring procedures,
- read-only domain researchers for noisy, bounded investigation surfaces.

Declared work graphs render to Workflow scripts under `.claude/workflows/`. Each node awaits only its own dependencies, so independent branches run concurrently, and every loop carries both an explicit termination condition and a hard iteration cap.

Generated workflow skills never pre-approve tools. Generated agents declare a capability tier - `reader`, `verifier`, or `implementer` - and the tier alone decides their tools and permission mode. A profile can never set them directly, so repository-controlled text cannot silently expand an agent's authority. `reader` is the default; `implementer` is the only tier that writes and requires both a declared writable scope and a recorded operator approval. Each agent records the session launch flags for its tier, so the boundary can be enforced by the process rather than only declared.

## Implementation transports

### `codex-plugin`

Preferred for Standard when OpenAI's official `codex@openai-codex` plugin is installed and initialized. The generated wrapper invokes `codex:codex-rescue` with a compact pointer to `.ai/specs/current-task.md`. The full contract stays on disk, avoiding duplicate context. The optional automatic review gate remains disabled.

### `codex-cli`

Direct `codex exec` with the spec on stdin and repository-scoped `workspace-write`. This transport is required for Fleet because it exposes deterministic worktree, directory, and lane-process control.

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
- Generated hooks deny or add context and never allow; the command a hook runs comes from the platform-protected settings file, not from repository text read at runtime.

# Changelog

## Unreleased

Phases 1 and 2 of the v1.0 harness upgrade. See `.ai/decisions/0001-harness-v1-architecture.md`.

### Fixed — platform-dependent rendering and validation

- **Generated packages were CRLF when rendered on Windows.** Every write went through
  text-mode translation, so `install-harness.sh` carried a carriage return into its shebang and
  would not run on Linux or macOS. All generated writes now force LF, and the validator rejects a
  package containing CRLF so the regression cannot ship again.
- **The manifest recorded native path separators.** A package rendered on Windows listed
  `.claude\skills\...`, and the validator's skill and agent scans match a `.claude/skills/`
  prefix — so frontmatter checks and the unsafe-Codex-default token scan were silently skipped,
  and the package still reported `OK`. Manifest paths are now POSIX on every platform.
- `check_installed.py` skipped hand-written agents and rules on Windows for the same reason, and
  `inspect_project.py` emitted native separators into `project-scan.json`. Both normalized.
- `validate_harness.py` resolves `bash` to an absolute path instead of passing the bare name.
  Windows resolves a bare command through System32 first, which reaches the WSL launcher; on a
  machine whose only distribution lacks `/bin/bash` that surfaced as a false installer syntax
  error. When no bash is available the check downgrades to a warning, as the `node` check does.
- The test suite invokes `sys.executable` rather than `python3`, which does not exist on Windows
  outside the Microsoft Store alias stub, and skips the two symlink tests where creating a
  symlink is privileged. The suite now runs clean on Windows as well as CI.

### Added — graph and loop engineering (phase 2)

- Optional `graphs` array in the project profile. Each entry declares one recurring multi-agent
  procedure as a directed acyclic graph of prompted nodes.
- `scripts/harness_graph.py`: validates graphs, computes topological levels, and emits the
  Workflow script. Rejects dependency cycles, unknown dependencies, duplicate node ids, and
  duplicate graph names, naming the offending nodes.
- Loop safety is structural, not advisory. `repeat_until` and `max_iterations` are only valid
  together, the cap is bounded to 2-20, and a generated loop breaks on a reported `done` and
  `log()`s when it stops at the cap.
- Generated Workflow scripts under `.claude/workflows/<name>.js`. Each node awaits only its own
  dependencies, so independent branches run concurrently instead of behind level barriers.
- Node prompts are escaped into the generated template literal, so project text cannot
  interpolate into the script.
- `## Work graphs` section in generated `CLAUDE.md`, listing each graph with its node count,
  level count, and loop caps.
- Validator check for missing scripts, orphaned scripts, a missing `export const meta`, a lost
  iteration cap, and invalid JavaScript. The JavaScript check is skipped with a warning when
  `node` is unavailable.
- `examples/fleet-codex-cli.json` declares a `cross-package-change` graph.
- Tests covering the CLI, rendered DAG structure, prompt escaping, six invalid-graph rejections,
  and three validator drift cases.

### Added — context budget (phase 1)

- Optional `context_policy` object in the project profile: a working token band, a ceiling
  action, work that must be isolated out of the main session, and standing context rules.
- `## Context budget` section in generated `AGENTS.md`, stating the band and what to do on
  reaching the ceiling.
- `## Context discipline` section in generated `CLAUDE.md`, listing what belongs in an isolated
  agent rather than the main session.
- Validator check rejecting a package whose profile lacks a normalized `context_policy`, or whose
  `AGENTS.md` or `CLAUDE.md` does not state the configured band, so the contract cannot drift
  from the profile.
- Tests covering rendered defaults, custom values, and six invalid-policy rejections.

### Changed

- `context_policy` defaults to a 150000-200000 token band with `checkpoint-and-handoff`.
  Profiles that omit it stay valid, so this release is backward compatible.
- `graphs` defaults to empty. A profile without graphs renders a `## Work graphs` section that
  explains how to declare one, and generates no scripts.


## 0.2.0 — 2026-08-27

### Added

- First-class **Greenfield / Create** flow for empty and planning-only project folders.
- Inspector `project_state` classification with `empty`, `minimal-planning`, `harness-only`, and `existing` states.
- Guided Greenfield interview covering problem, users, primary outcome, MVP scope, non-goals, workflows, stack direction, constraints, milestones, and open questions.
- Two Greenfield setup depths:
  - `context-only` for harness + durable project briefs,
  - `ready-to-build` for an additional reviewed first bootstrap contract.
- Greenfield artifacts under `.ai/project/`: product brief, planned architecture, roadmap, and open questions.
- Optional root project README generation.
- Greenfield-aware backlog and first scaffold specification.
- `examples/greenfield-standard.json`.
- Validation and installed-harness checks for Greenfield packages.
- Tests for blank-folder detection, README-only planning folders, Greenfield rendering, optional outputs, and invalid Greenfield configurations.

### Changed

- `/development-harness:setup` now explicitly supports `new`, `existing`, and `upgrade` entry paths.
- Create mode may start at Lite or Standard, but never Fleet.
- Planned Greenfield commands and paths are clearly distinguished from verified repository evidence.
- Git initialization, dependency installation, and application scaffolding remain manual and are never executed during setup.
- Generator and plugin version bumped to `0.2.0`.

## 0.1.0 — 2026-08-27

- Initial Claude Code marketplace plugin.
- Repository inspection and adaptive interview.
- Lite, Standard, and Fleet harness generation.
- Official Codex plugin, direct Codex CLI, and Claude-only transports.
- Conflict-aware installer, structural validator, and installed-harness checker.
- Project-specific scoped rules, workflow skills, and read-only domain researchers.

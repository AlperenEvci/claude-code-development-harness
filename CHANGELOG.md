# Changelog

## 1.0.0 — 2026-08-31

The v1.0 harness upgrade, phases 1 through 4. See
`.ai/decisions/0001-harness-v1-architecture.md` and
`.ai/decisions/0002-session-substrate.md`.

**Upgrading from 0.2.0 needs no migration.** The roadmap assumed v1.0 would be a
breaking schema change. It is not: every field added since — `context_policy`,
`graphs`, and an agent's `capability` — is optional and defaulted, and a profile
that names none of them renders exactly what 0.2.0 rendered. The three shipped
0.2.0 example profiles are frozen under `tests/fixtures/` and rendered and
validated on every run, so this stays true rather than merely having been true
on release day.

Re-render an existing harness to pick up the new sections; nothing in an
installed 0.2.0 harness stops working if you do not.

### Added — sessions, message bus, and agent synthesis (phase 4)

- `scripts/harness_session.py`: turns a capability tier into the exact command
  that enforces it, and sweeps background sessions the repository left running.
  `launch` prints the command and never runs it. `sweep` is dry-run by default,
  like the installer, and needs `--stop` to act.
- `scripts/harness_bus.py`: typed, append-only envelopes under
  `.ai/bus/<session-id>/`. Envelope kinds are `result`, `finding`, `question`,
  `handoff`, and `status`. Summary, body, and evidence are capped at write time,
  so the phase-1 context budget is enforced where agent output actually enters
  the main session rather than merely recommended.
- `scripts/harness_agentgen.py`: need → spec → validate → emit. Produces
  `claude --agents` JSON so a synthesized agent is ephemeral by default; writing
  one into `.claude/agents/` is a separate `promote` step that is dry-run and
  never overwrites. A need may not name `tools`, `permissionMode`, `isolation`,
  or any other authority key — those are refused by name, not ignored — and a
  synthesized `implementer` passes the same scope-and-approval gate as a
  declared one.
- Standard and Fleet harnesses install all four scripts under
  `scripts/ai-harness/`, copied verbatim. The validator rejects a copy that
  differs from the plugin original, so an installed harness cannot enforce
  capability tiers with code the test suite never saw.
- `## Agent sessions` section in generated `CLAUDE.md`, stating the dispatch
  rule per tier, the bus, synthesis, and the teardown sweep. The validator
  rejects a package whose `CLAUDE.md` omits the teardown step, because a missing
  teardown fails silently: nothing breaks, agents just accumulate.
- `references/agent-sessions.md`, loaded on demand by both skills.
- `.ai/reports/0001-session-substrate-smoke-test.md` records what was measured.
- `harness_session.py launch --restricted` additionally ignores user, project, and
  local settings files, for a session pointed at a repository you do not trust: a
  scanned project's `.claude/settings.json` is repository text, and repository text
  must never become tool permissions. It is not a default, and it is refused for
  `implementer`, which passes no `--tools` and would silently lose `Bash`.

### Added — release and compatibility guards

- The version is now pinned across `plugin.json`, the renderer's
  `GENERATOR_VERSION`, and the `CHANGELOG.md` heading. `AGENTS.md` has always
  forbidden bumping the manifest without a changelog entry; nothing enforced it,
  and a hardcoded version literal in the test would only have made the release
  edit one file longer. A release that forgets one of the three now fails.
- `tests/fixtures/v0.2-*.json` freeze the three shipped 0.2.0 example profiles.
  They are rendered and validated on every run, so backward compatibility is a
  guarantee rather than a claim.
- CI runs `bash scripts/validate-repo.sh` — the command `AGENTS.md` names as the
  full gate — instead of reimplementing a subset of it inline. The gate script had
  gone unexercised and rotted: it invoked `python3`, which on Windows resolves to
  the Microsoft Store alias stub, so the documented full gate could not run on the
  primary development machine and nothing noticed.
- `.gitattributes` makes the repository LF-only in the working copy as well as in
  the object store. With `core.autocrlf=true` a Windows clone checked out
  `scripts/validate-repo.sh` with CRLF, and a shell script whose lines end in `\r`
  fails in a way that reads as a broken gate rather than a broken checkout.

### Fixed — a read-only agent could not have reported from where it was told to run

- **Generated agent files told every tier to launch with `claude --bg`.** `--bg`
  refuses `--print`, so a background session has no structured result and can
  only report by writing a bus envelope — and `reader` and `verifier` have no
  `Write` tool to write one with. A reader launched as documented produced a
  session whose output was unreachable except as ANSI terminal capture. The
  launch command now follows the tier: writing tiers run detached, read-only
  tiers run in the foreground and the orchestrator reads their structured
  output. `harness_session.py` refuses to build the impossible command and the
  validator rejects an agent file that documents it.
- **The permission-bypass scan covered skills only.** The harness now generates
  runnable blocks in `CLAUDE.md` and in every agent file, so
  `--dangerously-skip-permissions` in a session launch line would have shipped
  unexamined. The scan now covers every generated markdown file. Prose is still
  exempt — a documented prohibition is not an unsafe default.
- `--allow-dangerously-skip-permissions` is named explicitly in the forbidden
  token list. It was already caught as a substring of the shorter flag, which
  reported the wrong flag name; the list is now ordered longest-first.

### Changed

- The launch flags for each tier are stored once as a list and the documented
  launch string is derived from it, so a tier cannot be documented one way and
  launched another. The rendered text is unchanged.
- `capability_grant_errors` moved into `harness_capabilities.py`. The renderer is
  no longer the only thing that hands out a tier — synthesis does too — and two
  copies of that rule would be two places for the writing tier to become
  reachable, only one of them reviewed.
- `harness_session.py sweep` never counts the session running it. A sweep is
  usually run by a background orchestrator, which `claude agents` lists like any
  other background session; without this the first thing a teardown step does is
  stop itself, abandoning the siblings it had not yet reached.

### Corrected

- `.ai/decisions/0002-session-substrate.md` listed `--bg` and
  `-p --output-format json` in one capability table as though they compose. They
  do not. The decision carries a dated correction rather than a silent edit.

### Added — agent catalog and capability tiers (phase 3)

- Generated project agents declare a **capability tier**: `reader` (default), `verifier`, or
  `implementer`. `reader` reproduces the pre-1.0 read-only agent exactly, so a profile that
  names no tier is unchanged.
- `scripts/harness_capabilities.py`: one tier table, imported by the renderer, the validator,
  and the installed-harness checker, so what writes authority and what checks it cannot drift.
- `verifier` gains `Bash` to run gates and inspect diffs but still denies `Write` and `Edit` and
  stays in `plan` mode.
- `implementer` is the only tier that writes, and reaching it requires both a non-empty
  `writable_paths` scope and `approved_by_operator: true`. Either one missing is a hard error.
  A non-writing tier that declares a writable scope is rejected as a contradiction.
- The tier is recorded in the agent's frontmatter as `capability:`, and every agent carries a
  `## Session launch` block with the flags for its tier, so the boundary can be enforced by the
  process rather than only declared in a file.
- The core `harness-codebase-researcher` and `harness-code-reviewer` agents are labelled
  `reader` and `verifier`, and the researcher now denies `Write`, `Edit`, and `Bash` explicitly.
- Validation compares the **whole** tool list against the tier rather than matching a prefix, so
  a staging package cannot be edited to append `Write` to a reader. The check covers every agent
  file in the payload, including hand-added ones, not only those the profile declares.
- `check_installed.py` rejects an installed agent whose declared read-only tier carries an
  edit-accepting permission mode, since the installed copy is the one that runs.
- `examples/standard-codex-plugin.json` gains a `verifier`; `examples/fleet-codex-cli.json`
  gains a scoped `implementer`.

### Changed

- The test asserting generated agents can never write was **rewritten, not removed**, per the
  compensating controls in `.ai/decisions/0001-harness-v1-architecture.md`. It now asserts the
  narrower property that still holds: a profile cannot set `tools`, `permission_mode`, or
  `isolation` directly, and cannot reach the writing tier without a declared scope and a
  recorded operator approval.

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

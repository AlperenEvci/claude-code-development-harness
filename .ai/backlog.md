# AI Backlog

## Harness v1.0 — four-phase upgrade

**Goal:** raise the harness from a static file generator to a system with a machine-checked context budget, explicit work graphs, a tiered agent catalog, and on-demand agent synthesis with an artifact message bus.

**Accepted architecture:** `.ai/decisions/0001-harness-v1-architecture.md` — hybrid (static generation plus a thin stateless stdlib CLI), capability-tiered agents, schema redesigned at 1.0.0, Rust rejected on measurement.

**Session model:** `.ai/decisions/0002-session-substrate.md` — build on `claude --bg` and `claude agents --json`; no tmux layer, no bespoke process manager.

### Completed

- Harness v0.2.0 adopted into this repository (Standard tier, `claude-only` transport, 23 files, zero conflicts).
- Architecture decision recorded and accepted, including the four compensating controls that make capability tiers safe.
- Rust evaluated against measurement and rejected for now: inspector runs in 0.205 s, 2723 lines of stdlib Python, zero dependencies, and the zero-build-step property is worth preserving.
- Session substrate settled against the real CLI surface: `claude --bg`, `claude agents --json`, `attach`/`logs`/`stop`/`rm`/`respawn`, `--session-id`, `--fork-session`, `--json-schema`, `--max-budget-usd`. A tmux layer was proposed and rejected; `--tmux` already exists as an operator convenience requiring `--worktree`.

### Remaining — deliver in order, repository green between phases

**Phase 1 — Context and prompt policy. DONE.** `context_policy` added to the profile (working band, `on_ceiling` action, `isolate_when`, `always`), rendered into a `## Context budget` section in `AGENTS.md` and a `## Context discipline` section in `CLAUDE.md`, with a validator check that rejects drift between the profile and the rendered contract. Optional and defaulted, so v0.2 profiles stay valid. Three tests added.

**Phase 2 — Graph and loop engineering.** Add graph and loop specs to the profile. Generate Workflow tool scripts under `.claude/workflows/`. Add `scripts/harness_graph.py` to validate a DAG, reject cycles, and emit a topological order. Loops need an explicit termination condition and an iteration cap.

**Phase 3 — Agent catalog and capability tiers.** Redesign the agent section of the schema around archetypes and skill pools. Implement `reader` / `implementer` / `verifier` tiers with tier-aware validation. Rewrite — do not delete — the tests that currently assert generated agents can never write. Per decision 0002, each tier records its **session launch flags** next to its frontmatter, so authority is enforced by the process (`--permission-mode`, `--tools`, `--restricted`, `--worktree`) rather than merely declared.

**Phase 4 — Dynamic agent synthesis, sessions, and A2A bus.** Depends on phases 1-3.

- `scripts/harness_agentgen.py` — need → spec → validate → emit. Emits `--agents <json>` for ephemeral use; writing into `.claude/agents/` is a separate operator-promoted step, so a synthesized `implementer` never lands in the repository implicitly.
- `scripts/harness_bus.py` — typed envelopes under `.ai/bus/<session-id>/`. Use `--json-schema` so session results arrive already validated against the envelope shape.
- Session model per decision 0002: `claude --bg` to start, `claude agents --json` as the single source of liveness, `attach`/`logs`/`stop`/`rm` for lifecycle. No parallel process table.
- Generate an explicit teardown step. Background sessions outlive their invoker; sweep with `claude agents --json --cwd <path>` and never leave orphans.
- Add `--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` to the validator's forbidden-token list, beside the existing Codex checks.
- **Smoke-test first.** The session flags were read from `claude --help`, not exercised. Verify `--bg`, `agents --json`, `logs`, and `stop` in a disposable fixture before treating the model as proven.

### Affected files

`plugins/development-harness/scripts/render_harness.py` (schema and rendering), `validate_harness.py` (tier-aware checks, required-file lists), `assets/templates/**` (new v1 layer files), `references/project-profile-schema.md` (rewrite), `examples/*.json` (regenerate — v0.2 profiles will no longer validate), `tests/test_plugin.py` (grow and rewrite), `CHANGELOG.md`, `plugins/development-harness/.claude-plugin/plugin.json`.

### Verification already run

- `python -m compileall -q plugins/development-harness/scripts tests` — passes.
- `python -m unittest discover -s tests -v` — **fails on Windows**, 21 of 24. Environmental, not a code defect.
- `bash scripts/validate-repo.sh` — not runnable on this machine.
- Installer syntax checked directly with Git Bash `bash -n` — passes.

### Known risks

- **Capability tiers relax a deliberate safety invariant.** All four compensating controls in decision 0001 must ship together with the tier work, or the relaxation is unsafe. Repository text is untrusted evidence; a synthesized agent must never choose its own authority.
- **v1.0 is a breaking schema change.** Existing v0.2 profiles stop validating; a migration path is required before release.
- **Windows cannot verify.** `tests/test_plugin.py` calls `python3` in 26 places (Microsoft Store alias stub), and symlink, chmod, and bash-installer tests need POSIX. `subprocess` cannot reach Git Bash either, because Windows `CreateProcess` searches System32 before PATH. Treat CI on `ubuntu-latest` as authoritative and never report a phase verified from a local run alone.

### Phase 1 verification

- `python -m compileall -q plugins/development-harness/scripts tests` — passes.
- Rendered defaults, custom values, and all six invalid-policy rejections verified directly on Windows by bypassing the validator step.
- Validator regression checks verified by calling `check_context_policy` in isolation: missing section, band drift, and absent policy are each caught.
- All three `examples/*.json` still render, including the two with no `context_policy` — backward compatibility holds.
- Full suite on Windows: 27 tests, 15 failing — all environmental, see Known risks.
- **CI green on ubuntu-latest: 27 tests, `OK`.** Run 33372597743 on commit `1afce62`. All three new context-policy tests pass. Phase 1 is verified against the authoritative gate.

### Repository

Work continues on a private copy, `AlperenEvci/claude-code-development-harness`.

- `origin` -> `AlperenEvci/...` (private, writable)
- `upstream` -> `egecan-af/...` (public, read-only; pull from it, never push to it)

GitHub cannot fork a public repository privately, so this is a mirror rather than a fork. There is no automatic link back to upstream: sync deliberately with `git fetch upstream`.

### Exact next step

Start Phase 2 on a feature branch: graph and loop engineering. Graph and loop specs in the profile, generated Workflow scripts under `.claude/workflows/`, and `scripts/harness_graph.py` for DAG validation with cycle rejection and topological ordering. Loops need an explicit termination condition and an iteration cap.

The two baseline commits went to `main` to establish the private repository. From Phase 2 onward, follow the repository's own `feature-branches` policy.

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

**Phase 2 — Graph and loop engineering. DONE.** Optional `graphs` array in the profile; `scripts/harness_graph.py` validates the DAG and emits the Workflow script; generated scripts land under `.claude/workflows/`. Cycles, unknown dependencies, and duplicate node or graph names are rejected by name. Loop safety is structural: `repeat_until` and `max_iterations` are only valid together, the cap is bounded to 2-20, and a generated loop breaks on `done` and `log()`s when it stops at the cap. Nodes await only their own dependencies, so independent branches run concurrently. Node prompts are escaped into the emitted template literal. `validate_harness.py` catches missing or orphaned scripts, a missing meta block, a lost cap, and invalid JavaScript. Six tests added.

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
- **Windows now verifies.** The suite runs clean locally: 39 tests, 2 skipped (symlink creation is privileged on Windows). Fixed by resolving `bash` to an absolute path, using `sys.executable` instead of `python3`, and normalizing generated line endings and path separators. CI on `ubuntu-latest` remains the authoritative gate, because the two skipped tests and the POSIX permission-bit assertion only run there.

### Phase 1 verification

- `python -m compileall -q plugins/development-harness/scripts tests` — passes.
- Rendered defaults, custom values, and all six invalid-policy rejections verified directly on Windows by bypassing the validator step.
- Validator regression checks verified by calling `check_context_policy` in isolation: missing section, band drift, and absent policy are each caught.
- All three `examples/*.json` still render, including the two with no `context_policy` — backward compatibility holds.
- Full suite on Windows: 27 tests, 15 failing — all environmental, see Known risks.
- **CI green on ubuntu-latest: 27 tests, `OK`.** Run 33372597743 on commit `1afce62`. All three new context-policy tests pass. Phase 1 is verified against the authoritative gate.

### Phase 2 verification

- `python -m compileall -q plugins/development-harness/scripts tests` — passes.
- All three `examples/*.json` still render, including the two with no `graphs` — backward compatibility holds.
- Validator drift cases verified locally: removed cap, invalid JavaScript, orphan script, and missing script are each caught.
- Full suite on Windows: 33 tests, 16 failing — the same environmental set as Phase 1 plus one new test that reaches `validate_harness.py`. See Known risks.
- **CI green on ubuntu-latest: 33 tests, `OK`.** Run 33374527893 on commit `0ccced4`, branch `phase-2-graph-loop`. All six new graph tests pass, including the `node --check` test, so the JavaScript check ran rather than being skipped.

### Platform-independence fix

Found while making the Windows suite runnable, and worth recording because two of these silently
weakened validation rather than failing loudly:

- Rendering on Windows produced CRLF, so `install-harness.sh` would not run on Linux or macOS.
- The manifest recorded native separators, so the validator's `.claude/skills/` and
  `.claude/agents/` prefix matches never fired. Frontmatter checks and the unsafe-Codex-default
  token scan were skipped and the package still reported `OK`.
- `check_installed.py` skipped hand-written agents and rules for the same reason.
- `validate_harness.py` passed the bare name `bash`, which Windows resolves through System32 to
  the WSL launcher.

A package rendered on Windows is now byte-identical to one rendered on Linux, and the validator
rejects CRLF so the regression cannot return.

### Repository

Work continues on a private copy, `AlperenEvci/claude-code-development-harness`.

- `origin` -> `AlperenEvci/...` (private, writable)
- `upstream` -> `egecan-af/...` (public, read-only; pull from it, never push to it)

GitHub cannot fork a public repository privately, so this is a mirror rather than a fork. There is no automatic link back to upstream: sync deliberately with `git fetch upstream`.

### Exact next step

Start Phase 3 on a feature branch: agent catalog and capability tiers. Redesign the agent section of the schema around archetypes and skill pools, implement `reader` / `implementer` / `verifier` with tier-aware validation, and record each tier's session launch flags next to its frontmatter so authority is enforced by the process. Rewrite — do not delete — the tests that currently assert generated agents can never write, and ship all four compensating controls from decision 0001 in the same change.

Phase 2 is on `phase-2-graph-loop` and green on CI. Merge it into `main` before starting Phase 3.

Note: `gh` resolves the bare repo from `upstream`, not `origin`. Always pass `-R AlperenEvci/claude-code-development-harness` when checking CI.

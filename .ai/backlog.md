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

**Phase 3 — Agent catalog and capability tiers. DONE.** Generated agents declare a `reader` / `verifier` / `implementer` tier, held in one shared table (`scripts/harness_capabilities.py`) imported by the renderer, validator, and installed-harness checker so authority and its enforcement cannot drift. `reader` is the default and reproduces the pre-1.0 agent exactly. All five compensating controls from decision 0001 shipped: an implementer must declare a non-empty `writable_paths` scope and carry `approved_by_operator: true`; validation is tier-aware and compares the whole tool list rather than a prefix, across every agent file in the payload rather than only profile-declared ones; the tier is recorded in frontmatter; and the read-only test was rewritten rather than deleted. Per decision 0002 each agent also carries its session launch flags, so the tier can be enforced by the process.

**Phase 4 — Dynamic agent synthesis, sessions, and A2A bus. DONE.** The session
substrate was smoke-tested first, as decision 0002 required
(`.ai/reports/0001-session-substrate-smoke-test.md`), and the measurement changed the
design: `--bg` and `-p` are mutually exclusive, so a background session has no
structured return channel and the message bus is its only way to report rather than a
convenience. Three scripts shipped — `harness_session.py` (tier-derived launch commands,
dry-run teardown sweep), `harness_bus.py` (append-only typed envelopes with write-time
size caps), and `harness_agentgen.py` (need → spec → validate → emit `--agents` JSON,
with `promote` as a separate dry-run step). Standard and Fleet install all four scripts
under `scripts/ai-harness/`, and the validator rejects a copy that differs from the
plugin original. Thirty-three tests added, each mutation-checked against its own source.

Two defects were found and fixed along the way, both of which had shipped in phase 3:

- Every generated agent file told its tier to launch with `claude --bg`, including
  read-only tiers that cannot report from a background session at all.
- The permission-bypass scan covered skills only, so a bypass flag in an agent's
  launch block or in `CLAUDE.md` would not have been seen.

### Remaining before a v1.0 release

- **Version bump.** `plugin.json` is still at `0.2.0`. Bumping it requires the matching
  `CHANGELOG.md` heading in the same change, and the release itself is the operator's
  call, so it was deliberately left alone.
- **Migration path.** The v0.2 → v1.0 story is still unwritten. In practice nothing
  broke: all three example profiles render and validate unchanged, and every new field
  is optional, so this may be a note rather than a migration.
- **`--restricted` is unexercised.** It would strip command-running tools from a
  `verifier` more thoroughly than `--tools` does. Worth measuring before relying on it.
- **`--max-budget-usd` is `--print`-only**, so it cannot bound a background lane.
  Whether an implementer lane needs a different ceiling is unresolved.

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

### Phase 3 verification

- `python -m compileall -q plugins/development-harness/scripts tests` — passes.
- Local Windows: 45 tests, 2 skipped (symlink privilege), no failures.
- All three `examples/*.json` render and validate, including the fleet profile's scoped `implementer`.
- Escalation cases verified by editing a rendered package: appending `Write` to a reader's tools,
  flipping its permission mode, dropping the `capability` line, shortening `disallowedTools`, and
  smuggling in an agent the profile never declared are each caught.
- The tools check was substring-based in the first draft and accepted an appended `Write`. Caught
  by its own test; it now compares the whole list.

### Phase 4 verification

- **`bash scripts/validate-repo.sh` now runs on Windows and passes end to end**: 78
  tests (2 skipped for symlink privilege), both JSON manifests, all three example
  profiles rendered and validated, and `claude plugin validate` green for the plugin
  and the marketplace. The gate itself had the same `python3` defect the test suite
  had — on Windows that name resolves to the Microsoft Store alias stub — so it now
  resolves an interpreter by running it rather than by finding it on PATH.
- The gate also renders and validates every `examples/*.json` now. Nothing checked
  that before, so a profile could have broken without any local signal.
- Each new guarantee was mutation-checked: the fix was reverted at its source and the
  test that should care was run. One test pinned nothing — it accepted a rejection
  from the generic unknown-key path — and was tightened to assert the specific
  refusal. All eight now fail when their fix is removed.
- Session lifecycle exercised against Claude Code 2.1.251 in a disposable fixture:
  `--bg`, `agents --json --cwd`, `--all`, `logs`, `stop`, `rm`, `-p --json-schema`,
  and `--agents`. A `reader` session was asked to write a file and was blocked twice
  over, with `Write` absent in subagents as well.

### Repository

Work continues on a private copy, `AlperenEvci/claude-code-development-harness`.

- `origin` -> `AlperenEvci/...` (private, writable)
- `upstream` -> `egecan-af/...` (public, read-only; pull from it, never push to it)

GitHub cannot fork a public repository privately, so this is a mirror rather than a fork. There is no automatic link back to upstream: sync deliberately with `git fetch upstream`.

### Exact next step

Phases 1-4 are complete and the repository is green locally. Nothing is committed:
git is the operator's.

1. Commit and push, then confirm CI on `ubuntu-latest` — still the authoritative gate,
   because the two symlink tests and the POSIX permission-bit assertion only run there.
2. Decide the v1.0 release: version bump plus the matching `CHANGELOG.md` heading, and
   the migration note if one is needed.

Note: `gh` resolves the bare repo from `upstream`, not `origin`. Always pass
`-R AlperenEvci/claude-code-development-harness` when checking CI.

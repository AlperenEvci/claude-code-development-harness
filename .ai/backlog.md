# AI Backlog

## Harness 2.0 - module roadmap

**Goal:** turn every guarantee the generated harness makes into something that fires
without being asked, and bring context, cost, and loop handling level with September
2026 practice.

**Accepted architecture:** `.ai/decisions/0004-harness-v2-architecture.md`
(accepted 2026-09-06, amended after 1.14.0). **Evidence:** `.ai/reports/0003-harness-engineering-review-2026-09.md`.

**Delivery rule:** one module per feature branch, one minor release per module,
repository green and CI-confirmed between modules, no agent commits. Every module
touches the renderer, the validator, tests, a reference, and the changelog together;
the file lists below are the expected blast radius, to be confirmed by the
template cartographer before editing.

### Module 0 - Ground truth before hooks (1.13.0) - DONE on Windows, CI pending

Shipped on branch `module-0-ground-truth`. Measured: plain `-p` loads `CLAUDE.md`;
`--bare` refuses OAuth before any API call and has no inverse flag, so it is refused by
name (`FORBIDDEN_LAUNCH_FLAGS`) rather than pinned (`.ai/reports/0004-bare-flag-smoke-test.md`).
The always-loaded contract measures 250-264 lines across the shipped examples against a
target under 200. `python_command` is in the profile, unconsumed. Gate green locally
(246 tests, 4 skipped); CI on ubuntu-latest still has to confirm.

Small, first, and it unblocks everything else.

- Measure `--bare` against the installed CLI: does an inverse flag exist, and does
  `-p` still load `CLAUDE.md` and `--agents` today? Record in a new
  `.ai/reports/0004-...` smoke test. Then pin `launch_argv` and assert it in a test.
- Add `claude plugin validate --strict` to `scripts/validate-repo.sh` (skipped with a
  notice when the CLI is absent, as today).
- Validator measures rendered `CLAUDE.md` + `AGENTS.md` line count and reports it;
  warning only until module 3 makes it a failure (it did, in 1.16.0).
- Profile gains `python_command` (default `python3`; setup writes `python` on
  Windows). Nothing consumes it until module 1, but the interview asks now.
- Files: `harness_session.py`, `validate_harness.py`, `render_harness.py`
  (`load_profile`), `references/project-profile-schema.md`, `skills/setup/SKILL.md`,
  `scripts/validate-repo.sh`, `tests/test_plugin.py`, `CHANGELOG.md`.

### Module 1 - Guarded hooks (1.14.0) - DONE on Windows, CI pending

Shipped on branch `module-0-ground-truth`. `hooks_policy: guarded` renders
`.claude/settings.json` and copies two hook scripts byte-identical into
`scripts/ai-harness/`; the policy requires Standard or Fleet. The guard denies and
never allows, and follows the profile's `agent_commit_policy` rather than carrying its
own. Measured against CLI 2.1.263 in `.ai/reports/0005-guarded-hooks-smoke-test.md`:
`.env` read denied with the reason reaching the model, ordinary read untouched, brief
in context at startup, existing settings file reported as a conflict. Validator gained
`check_hooks()` (13 mutation checks, 13 caught); `check_installed.py` reports the
installed-but-unwired state. Gate green locally (265 tests); CI still has to confirm.

Two hooks shipped rather than four, per decision 0004: "start with the `PreToolUse`
guards and `SessionStart` brief; add `PreCompact` and `Stop` once the first two are in
the gate." `hook_precompact.py` moved to module 2, where the checkpoint subcommand it
needs is built; `hook_stop.py` moved to module 6, where `commands.smallest_check` is
added.

**Deviation from decision 0004:** no sidecar and no installer change. The installer's
uniform conflict contract already reports and skips an existing
`.claude/settings.json`; a per-path exception in `INSTALL_SCRIPT` would add a branch to
the most sensitive script in the repository. `check_installed.py` detects the unwired
state instead.

- Shipped: `hook_guard.py`, `hook_session_start.py`,
  `common/.claude/settings.json.tmpl`, `references/hooks.md`, the `docs/runtime.md`
  hooks section, corrected `SECURITY.md` and `platform-notes.md` claims, and the eval
  case `found-hooks-are-reported-never-adopted`.
- Not done, deliberately: the Lite tier gets no hooks at all rather than the guard
  alone. Lite installs no `scripts/ai-harness/`, so the guard has nowhere to land, and
  building a second copy path for one script was not worth the branch.
- Not done: the eval cases named `guard-denies-secret-read` and
  `settings-conflict-is-reported-not-merged`. Both are measured directly in
  `.ai/reports/0005-...`, and the eval budget was better spent on the adoption seam
  this release opened.

### Module 2 - Compaction-native context policy (1.15.0) - DONE on Windows, CI pending

Shipped on branch `module-0-ground-truth`. The working band is now a launch flag:
`harness_session.py launch` passes the profile's ceiling to `claude --autocompact`,
and the ceiling is narrowed to the 100k-1M range that flag accepts. A third hook,
`hook_precompact.py`, records the compaction boundary through a new
`harness_checkpoint.py from-hook`; the brief reports the count and reads it as a
ceiling problem. Fourteen mutation checks, thirteen caught, the fourteenth found dead
code. Gate green locally (291 tests); CI still has to confirm.

Measured first, in `.ai/reports/0006-compaction-smoke-test.md`: what `--autocompact`
accepts, the `PreCompact` payload's actual fields, that one 51-turn run compacted
three times with `PreCompact` and `SessionStart:compact` pairing 1:1, and that a
path-scoped rule is genuinely absent when nothing matches it.

**Three deviations from the roadmap, each with the measurement that forced it:**

- **No `MODEL_WINDOWS` table.** The plan was to derive the band from the session
  model's context window and reject a band above it. There is no way to measure a
  model's window from the CLI, and a table of numbers read off documentation would be
  invention sitting in the file the validator trusts. `--autocompact`'s own 100k-1M
  range is the real constraint, is enforced by the platform, and was measured.
- **A boundary log, not a checkpoint.** The plan said `PreCompact` would write a
  handoff through `harness_checkpoint.py`. Three compactions in one 51-turn run made
  that wrong: it would put three machine-written directories in `.ai/runs/` per
  session. The log is one folding file per session under `.ai/runs/compaction/`, and
  `latest_checkpoint` deliberately cannot see it - nobody wrote it, and it carries no
  intent to resume from.
- **Only `important_paths` moved to a scoped rule, and only when the list is long.**
  `sensitive_areas` stays in the always-loaded contract: a path-scoped rule loads on a
  path match, and `echo secret > config.py` through `Bash` matches nothing, so moving
  safety content out would remove it from exactly the sessions most likely to need it.
  And the split is gated at 400 characters of description, because on all three
  shipped examples moving four short descriptions out made the contract *bigger* - the
  pointer sentence is longer than the text it replaces.

- Not done: `harness_report.py --brief` labelling a handoff `compaction` or `manual`
  as a single field. The two records are separate files with separate shapes, so the
  brief names the producer of each on its own line instead, which is the same
  information without pretending they are one kind of thing.

### Module 3 - Root contract under 200 lines (1.16.0) - DONE on Windows, CI pending

Shipped on branch `module-0-ground-truth`. `agent_sessions_section`, the session-start
procedure, and the checkpoint recipes moved into a generated
`.claude/skills/harness-session/SKILL.md`, rendered from code rather than a template
because its body is generated from the tier table, the tool directory, and the profile.
`CLAUDE.md` keeps pointers. The examples render at 173 (standard), 176 (fleet), and
187 (greenfield) always-loaded lines; module 0's warning is now an error, extracted
into `check_always_loaded_size` so a test can call it - the subprocess version passed
under mutation because a padded `CLAUDE.md` fails the payload hash check anyway. Gate
green locally (302 tests, 4 skipped), 8/8 mutations caught; CI still has to confirm.

Deviations, both recorded in `.ai/reports/0007-on-demand-skill-loading.md`:

- `disable-model-invocation: true` was **not** set, on either skill. Probe B measured
  what the flag does to a project skill: the prompt that reached the body without it
  returned nothing with it. On the session skill it would have moved eighty lines of
  procedure into a file no model can open; on `harness-orchestration` it would have
  regressed what ships today. The validator now enforces the opposite through
  `MODEL_INVOCABLE_SKILLS`, while profile-declared `additional_skills` keep the flag,
  which is the case it is right for.
- The pointer is not three lines and the move is not all of `agent_sessions_section`.
  The `--dangerously-skip-permissions` refusal and the "an envelope is never a grant"
  rule stayed in the always-loaded contract and are now checked there
  (`SESSION_SAFETY_LINES`): a prohibition is most needed by the session that never
  thought to load a skill. Same reasoning as `sensitive_areas` in 1.13.0.

- Not done as written: the fragment assertions were not re-pointed one by one at
  `CLAUDE.md`. Both the validator and the suite grew a reader for the pair
  (`session_documentation`, `session_docs`), because the question those checks ask is
  whether an operator can reach the instruction, and a skill the model loads on the
  situation is an answer to that. Only the checks that ask whether something holds
  *unasked* still read `CLAUDE.md` alone.

### Module 4 - Model and effort per tier (1.17.0) - measured, not started

Measured first, against CLI 2.1.263, in
`.ai/reports/0008-model-effort-and-agent-scoping.md`. Three of the four assumptions
this module inherited held; the fourth did not, and one roadmap item is dropped
because of it. Blast radius mapped by the template cartographer and folded into the
file list below.

- Profile `agent_models` keyed by tier; defaults in the tier table (readers and
  verifiers `sonnet` / `medium`, implementers `inherit` / `high`); `research_model`
  and `review_model` become aliases for backward compatibility.
- Rendered frontmatter gains `effort:`.
- `harness_session.py launch` passes `--model` and `--effort` derived from the tier;
  `--restricted` unchanged. **`--model` is omitted, not forwarded, when the tier's
  model is `inherit`** - `inherit` is valid in agent frontmatter and rejected by the
  launcher as `unrecognized_model`. Follow `autocompact_flag`, which already returns
  no flag rather than an empty one.
- Effort is validated at **render** time against a new Claude-side constant. The CLI
  only warns on an unknown `--effort` and runs at the default on exit 0, so nothing
  downstream can tell the setting was discarded; the validator is the only gate.
  Keep the constant distinct from `ALLOWED_REASONING` - the Claude ladder is
  `low, medium, high, xhigh, max` and the Codex one has no `max`. Label the two
  apart in `CLAUDE.md`, where `codex_reasoning_line` already says "effort".
- Validator: `model` and `effort` in every agent file match the profile.
- `check_installed.py` reports a project agent that shadows a generated one.
- **Dropped: `tools: Agent(<readers>)` on readers, and the validator check for it.**
  Measured: the specifier parses and restricts nothing - a probe declaring
  `Agent(probe-inner)` spawned `general-purpose` successfully. Shipping it would put
  a string in frontmatter that the platform ignores and then gate on its presence,
  claiming a containment property the package does not have. Same shape as module 3's
  `disable-model-invocation` finding. Dropping it also removes the whole-list tools
  assertions in `CapabilityTierTests` from the blast radius and retires the open
  question of which agents count as "readers".
  Related, for whenever reader-to-reader scoping is attempted again: the
  available-agent-types listing does not reach a subagent, so a grant expressed only
  in frontmatter is one the grantee cannot discover. It has to be in the prompt.
- Files: `harness_capabilities.py` (`CAPABILITY_TIERS`, three entries),
  `render_harness.py` (`load_profile` alias handling, `normalize_agent_capabilities`,
  an explicit `computed_context` key - a nested `agent_models` dict does not reach
  templates through the profile spread - the per-agent model validation, the
  forbidden-override set, and the frontmatter emitter), `harness_session.py`
  (`launch_argv` signature, argv assembly, `cmd_launch`, argparse),
  `harness_agentgen.py` (synthesized agents emit the same frontmatter and must gain
  `effort:` or a promoted agent fails the new check), `validate_harness.py`,
  `check_installed.py`, both agent templates under `standard/`,
  `common/CLAUDE.md.tmpl`, `references/harness-tiers.md`,
  `references/project-profile-schema.md`, `references/questionnaire.md`,
  `skills/setup/SKILL.md` (round 4 question changes shape), `docs/runtime.md`, the
  three examples, the three v0.2 fixtures (the alias regression surface), tests
  (target 10).
- Second-order: `harness_capabilities.py` and `harness_session.py` are copied
  byte-identically into `scripts/ai-harness/`, so manifests must regenerate. Patch
  with `write_bytes`; `write_text` emits CRLF and breaks the identity check.

### Module 5 - Envelope v3 and the cost reader (1.18.0)

- `ENVELOPE_VERSION = 3`; `trace` gains `cost_usd`, `cost_basis`, `model_usage`,
  `num_turns`, `subtype`. Versions 1 and 2 still read. Fields stay absent from the
  agent-facing schema.
- `launch --report` fills them from `total_cost_usd`, `modelUsage`, `num_turns`, and
  `subtype` in the result JSON; a field the CLI did not return stays absent.
- `harness_report.py --cost`: per unit of work, per model, cache hit ratio
  (`cache_read / (cache_read + input)`), and the launcher's `subtype` distribution.
  Text and HTML.
- Files: `harness_bus.py`, `harness_session.py`, `harness_report.py`, `docs/runtime.md`,
  `references/agent-sessions.md`, tests (target 10).

### Module 6 - Loop closure (1.19.0)

- Profile `commands.smoke` and `commands.smallest_check`; the interview asks for
  both and setup proposes them from the inspector's detected commands.
- `hook_session_start.py` runs the smoke command and prints one pass/fail line.
- `hook_stop.py` (deferred from module 1) - `Stop`: exits 0 immediately when
  `stop_hook_active` is set or the tree is unchanged; otherwise runs
  `commands.smallest_check` and blocks with the failing tail. Expects the
  platform's eight-block cap.
- `harness_progress.py claim <id>` / `release`: one claimed item per session recorded
  under `.ai/runs/current-task.json`; `--brief` shows it; `check` reports a stale
  claim.
- Files: `render_harness.py`, `harness_progress.py`, `harness_report.py`, the two hook
  scripts, `skills/setup/SKILL.md`, `references/questionnaire.md`, tests (target 8).

### Module 7 - Evals and release (2.0.0)

- Request `claude plugin eval` access; when it lands, `RUN_PLUGIN_EVAL=1` runs with
  `--max-cost-usd` and ablation on; record the first scored run as a report.
- New cases from modules 1 and 6; `session` and `agent` coverage via a pre-rendered
  fixture harness under `tests/fixtures/`.
- Flip `hooks_policy` default to `guarded`; the three examples regenerate; the
  frozen 0.2 and 1.x fixtures must still render and validate unchanged.
- Version 2.0.0 in `plugin.json`, `GENERATOR_VERSION`, `CHANGELOG.md`; decision 0004
  to accepted; `README.md`, `docs/architecture.md`, `docs/runtime.md` updated.

### Deliberately not in 2.0

Agent teams, prompt- or agent-type hooks, an MCP server, automatic commits, a process
supervisor or desktop shell, settings.json merging, and any hook that returns `allow`.

### Known risks

- A guard hook with a wrong matcher blocks legitimate work. Mitigation: escape hatch,
  narrow matchers, a test per deny rule and a test per allowed sibling.
- `Stop` fires on every response end. Mitigation: tree-changed check before any
  command runs; the cap is the platform's.
- Hook stdout is context. Mitigation: `--brief` output cap enforced in the script.
- `--bare` becoming the `-p` default would silently strip the contract from read-only
  lanes. Mitigation: module 0 measures and pins it before module 1 starts.
- Windows: exec form and `python_command`; both legs of CI must run the hook tests.

## After 2.0 - host portability (Claude Code, Codex, OpenCode)

**Status:** accepted as direction, not scheduled. Nothing here starts before 2.0.0
ships. Recorded now so the 2.0 modules do not quietly make it harder.

**Goal:** one rendered harness that Claude Code, Codex, and OpenCode each pick up
correctly, rather than one harness that works fully in Claude Code and partially
everywhere else.

**Where the seam already is.** Three layers exist in the generated package today, and
they do not port equally:

- *Host-neutral.* The `.ai/` tree and four of the runtime scripts - `harness_bus.py`,
  `harness_checkpoint.py`, `harness_progress.py`, `harness_report.py` - carry no CLI
  binding at all (checkpoint shells out to `git`, nothing more). Any host that can run
  Python can drive them.
- *Read by more than one host.* `AGENTS.md` is the engineering contract and Codex
  reads it unprompted. This is the existing portability surface and it works.
- *Claude Code only.* `harness_session.py launch` resolves the literal `claude`
  binary (`shutil.which("claude")`, argv `["claude"]`); guarded hooks are
  `.claude/settings.json` plus Claude's `PreToolUse` / `SessionStart` / `PreCompact`
  events; the on-demand session skill depends on Claude's description-matched skill
  loading; the working band is Claude's `--autocompact` flag. Everything modules 1, 2,
  and 3 added to make guarantees fire unasked lives here.

**The honest problem.** Codex delegation already ships (`implementation_delegate`:
`codex-plugin` / `codex-cli`), but in that model Claude is always the driver and Codex
only executes an accepted contract. Portability means something different: Codex or
OpenCode as the *host*, with the same guarantees firing. Those hosts have their own
configuration surfaces (`~/.codex/config.toml`, profiles, MCP) but not a
one-to-one equivalent of hooks, skills, and subagents. So this is not a rendering
change; it is a question about what a guarantee degrades into when the mechanism that
enforced it is absent.

**Measure before designing, same rule as every module so far.** The first unit of work
is a report, not code: for each of Codex CLI and OpenCode, what exists today for
(a) an always-loaded project contract, (b) a pre-tool-use deny hook, (c) a
session-start brief, (d) on-demand instruction loading, (e) subagents with a tool
allowlist, and (f) a compaction boundary signal. Record the version measured against.
No table of capabilities written from documentation.

**Design constraints, carried from decisions 0004 and 0001.**

- A guarantee that cannot fire on a host must be *reported as absent* by
  `check_installed.py`, never silently downgraded to prose that nobody enforces.
- No host gets a weaker safety floor. The bypass-flag refusals and the
  read-only-agent defaults are floors, not Claude Code implementation details.
- Rendering stays deterministic and dry-run-first. A second host is a second set of
  target paths, not a second installer.
- One template tree. If per-host output means forking `common/`, the design is wrong.

**Open questions to settle in the decision record, not in code.**

- Is the profile's `implementation_delegate` the right axis, or does a separate
  `hosts: [...]` field belong next to it? They answer different questions - who
  executes versus who drives - and conflating them is how the Fleet/`codex-cli`
  coupling happened.
- Does a single package install for every declared host at once, or does the operator
  render once per host? The first risks writing files a host will never read; the
  second risks two packages drifting.
- Does `harness_session.py` grow a host abstraction, or does each host get its own
  launcher? The launcher is the only script with a hard CLI binding, so it is the
  whole cost.

**Blocked on:** 2.0.0 shipped and CI-confirmed. Revisit the moment module 7 closes.

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

### v1.0.0 released

- **Version bumped to 1.0.0** in `plugin.json`, the renderer's `GENERATOR_VERSION`,
  and the `CHANGELOG.md` heading. A test now pins the three against each other, so
  the `AGENTS.md` rule against bumping the manifest without a changelog entry is
  enforced rather than merely written down. Verified by bumping the manifest alone
  and watching the test fail.
- **No migration is needed, and this was measured rather than assumed.** The three
  example profiles shipped with 0.2.0 were extracted from the pre-upgrade commit
  and rendered and validated with today's toolchain: all three pass unchanged. The
  recorded risk that "existing v0.2 profiles stop validating" is false — every
  field added since is optional and defaulted. The fixtures are frozen under
  `tests/fixtures/` and rendered on every run so this stays true.
- **`--restricted` measured, and it changed the design.** A session launched with
  `--restricted` and no `--tools` reports its tools as Read, Grep, Glob, **Write**:
  it strips code-running tools and WebFetch but not `Write`, so it cannot stand in
  for a read-only tier. Decision 0002 offered it as an alternative to
  `--tools Read,Grep,Glob,Bash`; that is now corrected. What it does add is
  settings-file isolation, which matters when the repository is untrusted, so it is
  an opt-in flag on `harness_session.py launch` and is refused for `implementer`.

### Still open

- **`--max-budget-usd` is `--print`-only**, so it cannot bound a background lane.
  Whether an implementer lane needs a different ceiling is unresolved. The current
  answer is the contract and the worktree, not a spend ceiling.
- **Publishing.** `docs/publishing.md` describes tagging and marketplace listing.
  The tag and any public release remain a deliberate operator action.

### From the external practice review

`.ai/reports/0002-external-practice-review.md` benchmarked this harness against
published work from Anthropic, Google, OpenAI, LangChain, and Matt Pocock, and found
five gaps. They are ordered by whether they change what the product *is*.

All five are now closed, across 1.2.0 through 1.6.0. What each one left behind is
recorded under its own entry, and none of it is a hole in the closure: the eval cases
still have no scored run because the runner is gated, the checkpoint token count is
caller-reported because no subprocess can observe its parent, the ledger deliberately
does not execute its own verify string, nothing yet consumes the envelope trace, and the
shape signals inform the audit and nothing else. That list is the honest successor to
this one - not a claim that the review is finished with.

1. ~~**No evals.**~~ **Started in 1.2.0, extended through 1.2.3.** Seven behavioral
   cases under `plugins/development-harness/evals/`, schema-checked on every push by
   `EvalCaseTests`, which now also refuses an absence grader that cannot fail and a
   `Skill` grader that cannot fire. Three things remain open.

   **The cases have never been executed.** `claude plugin eval` is early access and
   enabled per organization, so no scored run has confirmed that the graders match live
   behavior. This is the one that matters: everything below is coverage, and this is
   whether the coverage is real. Three releases in a row shipped a grader that always
   passed or always failed, each caught by reasoning or by a cheap probe rather than by
   a run — which is exactly the failure mode a run would have caught first.

   **`session` and `agent` are uncovered, and the blocker is fixture plumbing.** Both
   skills stop when `harness_session.py` or `harness_agentgen.py` is absent, and those
   arrive only by installing a rendered harness; a scaffold script runs in a stripped
   environment with no path back to the plugin root to copy one from. The way through is
   either a scaffold that can reach the plugin, or a pre-rendered harness checked in as
   fixture data. Neither is free.

   **`setup`'s interview is uncovered.** `setup-builds-nothing-before-the-dry-run`
   grades the prohibitions that hold with no answers at all, which is the safety half
   and the half that can be graded non-interactively. The interview itself — the part
   that decides what gets rendered — needs an answering party;
   `context.history_file` is the likely route in and has not been tried.
2. ~~**The context policy is a declaration with no mechanism.**~~ **Closed in 1.3.0.**
   `scripts/ai-harness/harness_checkpoint.py` reads the band and the declared action
   from the installed profile, exits 3 at the ceiling, and writes a structured handoff
   under `.ai/runs/` that refuses to omit a next step. What remains is the half no
   subprocess can do: the token count is caller-reported, because nothing running under
   a session can observe that session's window. Deep Agents' other half - offloading
   oversized tool results to the filesystem behind a reference - is a harness-level
   behavior this plugin cannot implement from outside, and is not on this list as a
   result. The original diagnosis follows.

   **The context policy is a declaration with no mechanism.**
   `context_policy.on_ceiling: "checkpoint-and-handoff"` is validated against the
   rendered Markdown and nothing else — the validator confirms the documentation
   matches the profile, which is two descriptions of an intention and no mechanism.
   Deep Agents implements both halves: offload tool results over ~20k tokens to the
   filesystem behind a reference and a short preview, and summarize at ~85% of the
   window into session intent, artifacts, and next steps. `.ai/runs/` is already the
   right home. Nothing writes a checkpoint into it.
3. ~~**Progress is Markdown prose, not a machine-checked ledger.**~~ **Closed in 1.4.0.**
   `.ai/progress.json` is the ledger and `harness_progress.py` maintains it: items start
   unproven, a pass requires the command and its exit status, a non-zero one is refused,
   and a hand-edited claim without evidence is rejected on read. `check` exits 3 while
   anything is unproven. The generated `CLAUDE.md` opens with the session-start checklist.
   The per-session checkpoint *commit* from Anthropic's write-up is deliberately not
   implemented: this harness does not commit on the user's behalf. The original diagnosis
   follows.

   **Progress is Markdown prose, not a machine-checked ledger.** Anthropic's
   long-running-harness work prescribes a JSON feature list as ground truth with every
   item `passes: false` until proven, a per-session checkpoint commit, and a mandatory
   session-start checklist. It also reports that models overwrite Markdown more readily
   than JSON — which is aimed squarely at this file.
4. ~~**Trace fields on the bus envelope**~~ **Closed in 1.5.0.** Envelope version 2
   carries an optional `trace` with a UUID correlation id, a duration, and token counts;
   `read --correlation <uuid>` returns one unit of work across sessions rather than one
   mailbox. Version-1 envelopes still read. The fields are set by the launcher through
   the CLI and are absent from the agent-facing schema, because an agent reporting its
   own token count is guessing and a guess recorded as a measurement is worse than a
   blank. What remains: nothing consumes the trace yet. Aggregating cost per unit of
   work, or feeding it to the eval loop, is a separate reader that does not exist.
   The original diagnosis follows.

   **Trace fields on the bus envelope** — correlation id, duration, tokens. The hard
   part (typed, append-only, capped, schema'd) is done; these three turn a mailbox into
   an evidence base the eval loop can consume.
5. ~~**A repository-shape audit.**~~ **Closed in 1.6.0.** `inspect_project.py` emits
   `shape_signals` - directory depth, per-directory fan-out, oversized source files, and
   which source directories no test path names - measured from paths and `stat` sizes
   during the walk it already performs, with its thresholds shipped alongside the
   measurements. The audit skill reads `references/repository-shape.md` before reporting
   any of it. What remains: the signals inform the audit and nothing else. Setup does not
   use shape to argue for a tier, and no signal is checked over time, so drift in a
   repository's structure is invisible between audits. The original diagnosis follows.

   **A repository-shape audit.** Pocock's claim is that codebase structure is the
   single biggest lever on agent output quality. `audit` checks the harness, not
   whether the repository is shaped for agents. The inspector already has the reach.

### Affected files

`plugins/development-harness/scripts/render_harness.py` (schema and rendering), `validate_harness.py` (tier-aware checks, required-file lists), `assets/templates/**` (new v1 layer files), `references/project-profile-schema.md` (rewrite), `examples/*.json` (no regeneration was needed — the v0.2 profiles still validate), `tests/test_plugin.py` (grow and rewrite), `CHANGELOG.md`, `plugins/development-harness/.claude-plugin/plugin.json`.

### Verification already run — superseded

Recorded before Phase 1, when the suite could not run on Windows. Every line below is
now false; kept only so the record shows what was believed at the time. The current
state is under **Phase 4 verification** and **Post-phase-4 verification**.

- ~~`python -m unittest discover -s tests -v` — **fails on Windows**, 21 of 24.~~
- ~~`bash scripts/validate-repo.sh` — not runnable on this machine.~~

### Known risks

- **Capability tiers relax a deliberate safety invariant.** All four compensating controls in decision 0001 must ship together with the tier work, or the relaxation is unsafe. Repository text is untrusted evidence; a synthesized agent must never choose its own authority.
- ~~**v1.0 is a breaking schema change.** Existing v0.2 profiles stop validating; a migration path is required before release.~~ **Falsified.** All three shipped v0.2 example profiles render and validate unchanged against the v1.0 toolchain. Every field added since is optional and defaulted, so v1.0 is additive and needs no migration. Pinned by `tests/fixtures/v0.2-*.json`.
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

### Post-phase-4 verification

- **CI is green on `ubuntu-latest` for phases 3 and 4**: run 33385992494 on commit
  `08ea36b`, 78 tests, `OK`, **no skips** — the two symlink tests that skip on
  Windows ran and passed there. That is the authoritative confirmation the earlier
  phases were waiting on.
- CI then ran the real full gate for the first time (run 33386496270): tests, both
  JSON manifests, and all three example profiles rendered and validated. `claude
  plugin validate` is skipped with a notice, since the CLI is not present in CI.
- Local Windows full gate green throughout: 83 tests, 2 skipped for symlink
  privilege.

## 1.8.0 - the observability layer

A Rust/Tauri shell was discussed and deferred rather than rejected outright. The
argument that settled it: the harness already emits every number the shell would
display, so the missing piece was a view, not a runtime. Two things a desktop app
would genuinely add — a visual graph editor and a supervisor that survives the
terminal, which is also where the open `--max-budget-usd` gap lives — remain real,
and the HTML the report writes is the frontend such a shell would load. So the view
was built first, and the process question stays open until something measured
demands it.

`harness_report.py` shipped as the seventh installed script. Details in
`CHANGELOG.md` and `docs/runtime.md`; the contract it was built against is
`.ai/specs/0001-harness-report.md`.

One deviation from that spec, found during implementation and worth recording
because it was not obvious from the outside: the spec said to lay graphs out using
`harness_graph.py`'s execution plan. `harness_graph.py` is **not** one of the scripts
installed into a target repository, so the installed copy would have failed to
import it. The layering is done locally instead, and the difference turned out to be
the right shape anyway — a validator must refuse a graph with a cycle, and a view
must still draw one, so the report reports what it could not order rather than
raising.

### Repository

Work continues on a private copy, `AlperenEvci/claude-code-development-harness`.

- `origin` -> `AlperenEvci/...` (private, writable)
- `upstream` -> `egecan-af/...` (public, read-only; pull from it, never push to it)

GitHub cannot fork a public repository privately, so this is a mirror rather than a fork. There is no automatic link back to upstream: sync deliberately with `git fetch upstream`.

### Exact next step

v1.0.0 is complete, committed, and CI-green. The remaining actions are release
actions, and they are deliberate operator choices rather than pending work:

1. Tag the release (`git tag v1.0.0`) if the private mirror should carry tags.
2. Decide whether any of this goes back upstream to `egecan-af/...`. There is no
   automatic link; a sync is a deliberate `git fetch upstream` plus a PR.

Note: `gh` resolves the bare repo from `upstream`, not `origin`. Always pass
`-R AlperenEvci/claude-code-development-harness` when checking CI.

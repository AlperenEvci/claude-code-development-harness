# Decision 0004: Harness 2.0 architecture

Date: 2026-09-06
Status: accepted; shipped in 2.0.0 on 2026-09-07 (see the amendments in place)

## Context

`.ai/reports/0003-harness-engineering-review-2026-09.md` benchmarked 1.12.0 against
primary sources fetched on 2026-09-06 and found the baseline had moved under the
harness. The five gaps from the 2026-08-31 review are closed, but every guarantee the
generated harness makes in routing, context management, and loop engineering is still
model discipline: a command the model must remember to run. Anthropic's 2026 guidance
now draws the line explicitly - an instruction in `CLAUDE.md` is a request, a
`PreToolUse` hook is enforcement - and native compaction, per-agent `model` and
`effort`, cost fields in every result record, and path-scoped rules all exist and are
unused here.

Version 1.0 turned prose into mechanism inside the scripts. Version 2.0 turns the
scripts into things that fire without being asked.

## Decision

### 1. The generated harness ships hooks, authored by the plugin, never adopted from the target

A third `hooks_policy` value, `guarded`, renders `.claude/settings.json` into the
payload with command-type hooks that call stdlib scripts installed byte-identical under
`scripts/ai-harness/hooks/`. The untrusted-text rule is unchanged: a hook found in a
scanned repository is evidence and is never promoted. A hook the renderer emits from
its own template is the plugin's output, in the same trust class as the tier table.

Invariants, each enforced by the validator and `check_installed.py`:

- Hooks only deny, inject context, or rewrite tool input toward less output. No hook
  ever returns `allow`, and no hook widens a permission.
- Command hooks only. `prompt` and `agent` hook types are refused; they add latency,
  call a model, and one of them is experimental.
- Exec form (`args: []`) everywhere, so Windows and POSIX run the same file, and the
  interpreter comes from a profile field rather than a bare `python3`.
- The installer treats an existing `.claude/settings.json` as a conflict: it is
  reported and skipped, never merged, never overwritten.
  *(Amended 2026-09-06, after 1.14.0 shipped: the sidecar
  `.claude/settings.harness.json` this originally required was not written and the
  installer was not changed. Its uniform conflict contract already reports and skips
  the file, and a per-path exception inside `INSTALL_SCRIPT` would add a branch to
  the most sensitive script in the repository to save an operator one `cat` of a file
  the package already contains. The part that was genuinely missing was detection:
  installed-but-unwired is otherwise indistinguishable from working, so
  `check_installed.py` now reports it.)*
- Every guard honors one escape, `HARNESS_HOOKS_DISABLE=1`, and the runtime guide names
  `disableAllHooks` beside it. A buggy matcher must not be able to lock an operator out
  of their own repository.
- Stop hooks read `stop_hook_active`, run only when the working tree changed since the
  turn began, and expect the platform's eight-block cap.
  *(Amended 2026-09-07, measured in `.ai/reports/0010-stop-hook-smoke-test.md`: the
  cap is nine, and a capped run returns an empty result with `subtype: success`, so
  honoring the flag is the whole hook and the launcher refuses to record an empty
  result. The tree comparison is against the fingerprint the check last passed on,
  not against the start of the turn.)*

`guarded` becomes the default in 2.0.0. That default change, not a schema break, is
what makes 2.0 a major version.
*(Shipped 2026-09-07: the default follows the tier, `guarded` at Standard and Fleet
and `examples-only` at Lite, because `guarded` is refused at Lite and a default the
renderer would refuse is not a default. A named policy is honored at any tier. The
frozen fixtures name theirs, so they render unchanged. `check_installed.py` re-checks
after installation that a handler's flag value equals the profile's command and that
no installed hook script mentions a permission decision.)*

### 2. Context policy is compaction-native

The 150k-200k band with a caller-reported `--used` stays as the fallback. The primary
mechanism is event-driven: `PreCompact` writes the handoff through
`harness_checkpoint.py`, and `SessionStart` with the `compact` and `resume` matchers
reads it back through `harness_report.py --brief`. The band is derived from the
session model's window in a table in `harness_capabilities.py`, because Sonnet 5 is 1M
native and a static band is wrong for it in both directions.

Sensitive paths and important paths move out of the root contract into path-scoped
`.claude/rules/*.md` with `paths:` frontmatter, which load only when a matching file is
read and are re-injected after compaction.

### 3. The generated root contract is under 200 lines, measured

`CLAUDE.md` plus its `@AGENTS.md` import is measured by the validator after rendering
and must stay under 200 lines. Procedure moves into on-demand skills: the agent-sessions
section becomes the body of a generated `harness-session` skill. Generated skills that
carry side effects declare `disable-model-invocation: true`.

### 4. Model and effort are per tier, explicit, and never `inherit` by default for readers

The profile gains `agent_models`, keyed by tier, each carrying `model` and `effort`.
Defaults: readers `sonnet` / `medium`, verifiers `sonnet` / `medium`, implementers
`inherit` / `high`. The tier table owns the defaults so the renderer, validator,
launcher, and `check_installed.py` cannot disagree. Readers also carry
`tools: Agent(<reader names>)` so a researcher cannot spawn a writer. Effort is swept
before a model is stepped down, and the eval suite is the thing that approves a step
down; that order comes from Anthropic's own cost-optimization measurements.

### 5. Envelope version 3 carries what the result record already provides

`trace` gains `cost_usd`, `cost_basis`, `model_usage` (per model: input, output, cache
read, cache creation, cost), `num_turns`, and `subtype`. The launcher fills them from
the JSON it already parses; nothing is estimated or synthesized. Versions 1 and 2 still
read. `harness_report.py --cost` aggregates per unit of work and reports cache hit
ratio, the one number Anthropic says to treat like uptime.

### 6. The loop closes at both ends

The profile gains `commands.smoke` and `commands.smallest_check` *(shipped in 1.19.0
as the flat keys `smoke_command` and `smallest_check_command`, matching every other
`*_command` key; the commands are rendered into `.claude/settings.json` as hook
arguments rather than read from the profile at runtime, because the platform protects
the settings file from a session's edits and does not protect the profile)*. `SessionStart`
runs the smoke command and reports one line; `Stop` runs the smallest check when the
tree changed. `harness_progress.py claim` records the one item a session is working
on under `.ai/runs/`, and `--brief` shows it, so one task per session is a recorded
fact rather than advice.

### 7. Delivery shape

Each module ships as its own minor release on `main`, repository green between
modules, one feature branch per module, no commits by the agent *(the operator later
authorized the agent to commit, push, and merge each module's branch; CI on ubuntu and
windows stayed the gate between modules)*. 2.0.0 is the release
that flips the `hooks_policy` default and declares the compaction-native policy. All
schema additions are optional and defaulted, so every 0.2 and 1.x profile still renders
and validates; this is asserted by the frozen fixtures, as it was for 1.0.

## Alternatives considered

- **Keep hooks out and strengthen prose.** Rejected. The 1.12.0 changelog already
  records why: a checklist of three is three chances to skip one. The field's
  consensus stack is five hooks, and Anthropic's own security plugin ships one.
- **Merge into an existing `settings.json`.** Rejected. Merging JSON the plugin did not
  write is the silent-overwrite failure in a different shape. Conflict and skip.
  *(The sidecar this line also proposed was dropped in 1.14.0; see the amendment
  under decision 1.)*
- **Prompt or agent hooks for the Stop gate.** Rejected for 2.0. A deterministic check
  the profile already names is cheaper, reproducible, and never wrong about what it ran.
- **Agent teams as a tier.** Rejected. Experimental, roughly seven times the tokens in
  plan mode, and enabling them turns every named subagent into a teammate. Emitted
  workflows remain the sanctioned path for parallel work.
- **Own process supervisor or desktop shell.** Still deferred, per decision 0001 and the
  1.8.0 note. Hooks remove the strongest argument for one.
- **Automatic per-session commit.** Rejected again. The harness does not commit on the
  user's behalf.

## Consequences

- The renderer, validator, `check_installed.py`, and the installer all learn about
  `settings.json`. That is the largest single surface added since 1.0 and touches the
  most sensitive file in the repository; it is module 1 and gets the deepest review.
- Hook stdout enters context on `SessionStart`, so `--brief` output is capped.
- A `-p` launch must be pinned against the announced `--bare` default before any hook
  work is trusted, because `--bare` skips hooks, agents, and `CLAUDE.md`.
- Windows parity is a first-class requirement for every hook: exec form, interpreter
  from the profile, tests that run on both.
- The two symlink tests and the POSIX permission-bit assertion still run only on CI;
  CI stays the authoritative gate.

## Evidence

- `.ai/reports/0003-harness-engineering-review-2026-09.md` and its sources.
- `.ai/reports/0002-external-practice-review.md` for the gaps 1.x closed.
- `.ai/decisions/0001-harness-v1-architecture.md` for the hybrid architecture this
  extends and the compensating controls that stay in force.
- `.ai/decisions/0002-session-substrate.md` for why the bus is the return path of a
  background lane.

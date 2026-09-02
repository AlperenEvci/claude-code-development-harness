# Implementation Spec: `session launch --correlation` and the launcher-written envelope

## Goal

An operator dispatches a read-only tier and gets a bus record without writing one
by hand:

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability reader --task "Map how billing retries are wired" \
  --exec --report --correlation 4c1d8a90-3e77-42bb-9a55-0f6de2b71c84
```

When that returns, `.ai/bus/<session-uuid>/0001-result-<short>.json` exists, carries
the tier the session ran under, and carries a `trace` with the correlation id and the
run's measured duration and token counts. `harness_report.py` then groups that work
unit with every other envelope sharing the correlation id, with no human step in
between.

Today the same outcome takes four manual actions: mint a UUID, run the session, reshape
its `structured_output` with the `python -c` one-liner in `docs/runtime.md:624`, and
call `harness_bus.py post`.

## Current context

Facts an execution agent needs, all verified in the tree at `main`:

| Fact | Where |
|---|---|
| `launch` accepts `--capability --task --session-id --background --worktree --scope --restricted --surface --lane --json --exec`. It has **no** `--root` and **no** `--correlation`. | `harness_session.py:706-757` |
| `--exec` calls `run_launch`, which refuses any tier whose `writes` is true, then `subprocess.run(..., capture_output=True)` and returns the child's exit code. It posts nothing. | `harness_session.py:511-540` |
| `launch_argv` builds `["claude", ...tier launch_flags..., task]`. It never emits `-p`, `--output-format`, or `--json-schema`. | `harness_session.py:254-364` |
| `harness_capabilities.launch_command()` documents the non-writing form as `claude -p <flags> --output-format json`. The printed argv and this documented string therefore disagree today. | `harness_capabilities.py:106-118` |
| The envelope JSON Schema is available in-process as `envelope_schema()`, and on the CLI as `harness_bus.py schema`. | `harness_bus.py:106+` |
| `build_envelope(...)` takes `correlation_id`, `duration_ms`, `tokens_in`, `tokens_out` and assembles `trace` via `normalize_trace`, which yields `null` rather than an empty object when nothing was measured. | `harness_bus.py:229-314` |
| `write_envelope` derives its sequence number from disk, refuses to overwrite, and requires the session directory name to be a plain UUID. | `harness_bus.py:377-404` |
| `sender` must match `AGENT_NAME_PATTERN` (lowercase-hyphen). `capability` must be a known tier and is recorded as a *claim*, never a grant. | `harness_bus.py:251-293` |
| `summary` is capped at 200 chars, `body` at 64 KB, `evidence` at 50 items. | `harness_bus.py:70-73` |
| `harness_session.py` and `harness_bus.py` are both in the six-file verbatim copy list installed into Standard/Fleet repos. | `render_harness.py:941-946` |
| Decision 0002: `--bg` and `-p` are mutually exclusive; a background session reports only by writing its own envelope, and a read-only tier has no `Write` tool to write one with. | `.ai/decisions/0002-session-substrate.md:107-123` |

The gap this closes is the one named in the research: the report is organised around
`correlation_id`, but nothing in the dispatch path produces one.

## Required behavior

### R1 — `--correlation` on `launch`

A new optional `--correlation <uuid>` argument. Accepted on both surfaces and with or
without `--exec`.

- The value must match the same UUID pattern the bus already enforces. A malformed
  value is refused by name, not normalized.
- If `--report` (R3) is given without `--correlation`, the launcher mints one.
- The effective correlation id is always printed to **stderr** as a single line so it
  can be threaded into the next dispatch, and it never contaminates the argv printed on
  stdout:
  `# correlation: 4c1d8a90-3e77-42bb-9a55-0f6de2b71c84`
- With `--json`, the correlation id appears in the emitted object. On the inproc
  surface `--json` currently prints a bare argv array; it becomes
  `{"argv": [...], "correlation_id": "..."}` **only when a correlation id is in
  effect**, so existing callers that pass no correlation see the unchanged array.

Rationale for minting rather than requiring: the operator should not have to run
`uuidgen` to get the grouping the report is built on, and a correlation id the
launcher printed is one the operator can reuse verbatim.

### R2 — Print mode is added on the `--exec` path only

`--exec` on the inproc surface additionally passes `-p` and `--output-format json`
before the prompt, because a run whose output must be parsed has to be a print-mode
run. `--json-schema <envelope schema>` is added as well, and only when `--report` is
in effect.

The **printed** command (no `--exec`) is unchanged. This is deliberate and must be
asserted by a test: a printed command is for a human to run interactively, and
`-p` would turn it into a one-shot the operator cannot converse with. `--exec` is the
programmatic path and is the only one that needs machine-readable output.

The schema comes from importing `harness_bus.envelope_schema()` directly, in the same
sibling-module style already used for `harness_capabilities`. Do not shell out to
`harness_bus.py schema`, and do not copy the schema into this module.

### R3 — `--report` writes exactly one envelope, from the launcher

A new `--report` flag, valid only together with `--exec`, and only on the inproc
surface for a tier whose `writes` is false. Any other combination is refused by name:

- `--report` without `--exec` → refused; there is no run to report on.
- `--report` with a writing tier → refused; `run_launch` already refuses those, and a
  writing tier posts its own envelope.
- `--report` with `--surface orca` → refused; the Orca surface returns terminal
  state, never structured output, and decision 0003 forbids parsing it.
- `--report` with `--background` → already impossible for a read-only tier
  (`launch_argv:284-293`); no new gate needed, but the refusal must stay reachable.

On a successful run the launcher posts one envelope with:

- `session_id` — the session UUID the launch used.
- `from` — `--report-from <name>`, defaulting to the capability tier name
  (`reader` / `verifier`), which already satisfies `AGENT_NAME_PATTERN`.
- `capability` — the tier that was launched.
- `kind`, `summary`, `body`, `evidence`, `next` — taken **only** from the agent's
  `structured_output`, which the schema in R2 shaped.
- `task` — the `--task` string.
- `trace` — the correlation id plus what the launcher measured (R4).

`--root <path>` is added to `launch` (default `.`, matching `list` and `sweep`) because
posting needs a repository root.

### R4 — The trace is measured by the launcher, never asked of the agent

`duration_ms` is wall-clock around the `subprocess.run` call, measured with
`time.monotonic_ns()`. Token counts are read from the CLI's own JSON result object.

Parse defensively. Read the usage numbers from the result envelope the CLI returns and
accept the plausible field spellings for input and output tokens; when a number is
absent or not an integer, **omit it** rather than substituting zero. `normalize_trace`
already renders an unmeasured field differently from a zero one, and that distinction
must survive.

The agent is never asked for these numbers. The `--json-schema` passed in R2 is the
bus envelope schema, which does not offer `trace` fields at all, so an agent has no
route to reporting its own cost.

### R5 — A run that produced nothing parseable posts nothing

If the child exits non-zero, or its stdout is not JSON, or the JSON carries no
`structured_output`, or the structured output fails `build_envelope` validation:

- no envelope is written,
- a single-line reason is printed to stderr naming which of those it was,
- the child's stdout and stderr are still relayed as they are today,
- the launcher returns the child's exit code, or `1` if the child succeeded but
  nothing could be recorded.

An invented summary is worse than a missing record. This module must never synthesize
envelope content it did not receive.

### R6 — The envelope is written through the existing bus code

Use `harness_bus.build_envelope` and `harness_bus.write_envelope`. Do not construct the
dict inline, do not write the file directly, and do not add a second copy of any cap or
pattern. Every limit — summary length, body size, evidence count, sender pattern, kind
vocabulary — must be enforced by the code that already enforces it, so a future change
to a cap reaches this path automatically.

A `BusError` from either call is an R5 outcome: report the message, write nothing.

### R7 — The path taken is stated, not implied

On a `--report` run the launcher prints to stderr, after the child returns, one line
naming the envelope it wrote relative to the root, or the reason it wrote none. An
operator must never have to list `.ai/bus/` to find out whether the loop closed.

### R8 — Documentation follows the behavior

- `docs/runtime.md` — replace the manual `python -c` reshaping step in the worked pass
  (`:614-645`) with the single `--exec --report --correlation` command, and keep the
  manual route documented directly beneath it as the fallback for a run this path
  refuses.
- `plugins/development-harness/skills/session/SKILL.md` — add `--correlation`,
  `--report`, `--root`, and the refusal matrix from R3. Keep it short; long-form goes
  in `docs/runtime.md`.
- `README.md` — the `### 5. Agent sessions...` section gains the one-command form.
- `CHANGELOG.md` and `plugins/development-harness/.claude-plugin/plugin.json` — one
  minor bump, both in the same change. The repository contract requires it.

## Scope

### Owns

- `plugins/development-harness/scripts/harness_session.py`
- `tests/test_plugin.py` (new cases only; do not rewrite existing ones)
- `docs/runtime.md`
- `plugins/development-harness/skills/session/SKILL.md`
- `README.md`
- `CHANGELOG.md`
- `plugins/development-harness/.claude-plugin/plugin.json` (version line only)

### Must not touch

- `plugins/development-harness/scripts/harness_capabilities.py` — the tier table is the
  authority boundary. Nothing here needs a new tier, a new flag in `launch_flags`, or a
  change to `writes`. If this work appears to need one, stop and escalate.
- `plugins/development-harness/scripts/harness_bus.py` — this spec is a caller of the
  bus, not a change to it. `build_envelope`, `write_envelope`, the caps, and the schema
  stay exactly as they are.
- `harness_progress.py`, `harness_checkpoint.py`, `harness_agentgen.py`,
  `harness_report.py`.
- `render_harness.py`, `validate_harness.py`, `check_installed.py` — the file is copied
  verbatim and checked by SHA, so no renderer or validator change is required. Confirm
  this by running the gate rather than by editing them.
- Anything under `assets/templates/`.
- `.ai/decisions/` — a decision record is written only if a rejected option here turns
  out to be load-bearing, and that is the operator's call, not the delegate's.

## Constraints

- **Standard library only.** No new third-party dependency, no package manifest.
- **No daemon, no supervisor, no background thread.** Decisions 0001 and 0002 rejected a
  runtime supervisor; this is a foreground subprocess the caller already owns, and it
  must stay that way.
- **`claude agents --json` remains the only registry.** This change writes to the bus,
  never to a parallel session table.
- **Verbatim-copy contract.** `harness_session.py` is installed byte-for-byte into every
  generated Standard/Fleet repository and `validate_harness.py` rejects drift by
  SHA-256. An edit here ships to every generated harness, so behavior must be
  backward-compatible: every existing invocation that passes neither `--correlation`
  nor `--report` must produce byte-identical output to today.
- **Cross-module import direction.** `harness_session.py` may import `harness_bus`; the
  reverse must not appear. Both already sit in the same installed directory.
- **Untrusted content.** `structured_output` is agent-written text. It is validated by
  the bus and recorded as evidence. Nothing in it may influence the argv, the tier, the
  root, or the correlation id.
- **Windows-primary local development, Linux-authoritative CI.** No POSIX-only
  assumption in new code or tests.

## Acceptance criteria

1. `launch --capability reader --task X` with no new flags prints exactly what it
   prints today, asserted against the current string.
2. `--correlation <bad>` is refused with exit 2 and a message naming the value.
3. `--exec --report` without a correlation mints one, and the same UUID appears in the
   stderr line and in the written envelope's `trace.correlation_id`.
4. `--report` without `--exec` is refused; `--report` with `--surface orca` is refused;
   `--report --capability implementer` is refused. Each refusal names its reason.
5. With a stubbed `claude` returning a well-formed result, exactly one envelope is
   written under `.ai/bus/<session-id>/`, it passes `harness_bus.py validate --root .`,
   its `capability` equals the launched tier, and its `from` defaults to the tier name.
6. `trace.duration_ms` is a positive integer measured by the launcher; token fields
   present in the stub appear, and token fields absent from the stub are absent from
   the trace rather than zero.
7. A stub whose stdout is not JSON, one with no `structured_output`, and one whose
   structured output violates a bus cap each write **no** envelope, print a reason, and
   return non-zero.
8. `--exec` argv contains `-p --output-format json`, and contains `--json-schema` only
   when `--report` is in effect.
9. `harness_report.py --json` on a repository containing the written envelope groups it
   under its correlation id.
10. The full gate passes, including the SHA-drift check for the copied runtime.

## Verification

```bash
python -m compileall -q plugins/development-harness/scripts tests
python -m unittest discover -s tests -v
bash scripts/validate-repo.sh
```

The suite must be run before and after, and the before-count recorded, so a new
failure is distinguishable from a pre-existing one. Two symlink tests skip on Windows
and one POSIX permission assertion only runs on Linux; confirm the result against CI
before calling the work verified.

## Report format

Return:

- changed files,
- behavior implemented, with the refusal matrix from R3 listed explicitly,
- test count before and after, and the exact commands run with their exit codes,
- any place the CLI's actual JSON result shape differed from what R4 assumed,
- unresolved concerns.

# Runtime guide

How to actually drive a 2.0 harness: capability tiers, agent sessions, the message
bus, on-demand agent synthesis, work graphs, hooks, and the context budget.

This is the operator-facing guide. The agent-facing version, loaded on demand by the
generated skills, is
[`references/agent-sessions.md`](../plugins/development-harness/references/agent-sessions.md).
The measurements behind both are in
[`.ai/reports/0001-session-substrate-smoke-test.md`](../.ai/reports/0001-session-substrate-smoke-test.md).

Every claim about CLI behavior below was produced by running Claude Code 2.1.251
for the session runtime and 2.1.263 for the hooks, not by reading `--help`. Five of
them reversed a design decision that had already been written down; the reports
under `.ai/reports/` record each one.

## What gets installed

A **Standard** or **Fleet** harness installs seven stdlib-only scripts:

```text
scripts/ai-harness/
├── harness_capabilities.py   # the tier table: tools, permission mode, launch flags, model, effort
├── harness_session.py        # launch specifications, listing, teardown sweep
├── harness_bus.py            # append-only typed envelopes under .ai/bus/
├── harness_agentgen.py       # need -> spec -> validate -> emit an agent
├── harness_checkpoint.py     # the context band, and the handoff under .ai/runs/
├── harness_progress.py       # the ledger of what is actually proven
└── harness_report.py         # the reader: joins all of the above into one page
```

Six of them write. `harness_report.py` is the only one that does not, and it was
added last for the reason that usually produces a tool like it: everything above
had been recording faithfully for six releases into four different trees, and the
only way to read the result was to open the files one at a time.

**Lite installs none of them.** Lite has no generated agents, so it gets nothing to
manage them with.

They are copied verbatim rather than rendered from templates, so the code in your
repository is the code the plugin's own test suite ran against. `validate_harness.py`
compares each installed copy to its plugin original by SHA-256 and rejects a package
whose copy has drifted.

### Where the procedure lives

Everything in this guide has a shorter form inside the installed repository, and
since 1.16.0 it is in two places rather than one.

`CLAUDE.md` and the `AGENTS.md` it imports are the **always-loaded contract**. Both
load at launch, into every session, before anything is asked. That makes them
expensive and makes them reliable, and the two facts pull against each other: the
platform's guidance is to keep an always-loaded file under 200 lines, and every tier
this generator shipped through 1.15.0 was over it at 250-264. `validate_harness.py`
now fails a package at 200 combined lines rather than warning.

`.claude/skills/harness-session/SKILL.md` is the **on-demand** half: how to launch an
agent, hand off through the bus, synthesize a one-off agent, read the report, write a
checkpoint, and sweep. Only its `description` line stays always-loaded. Measured on
2.1.263 against a fixture skill carrying a codeword: the model reached the body from
the description alone with nothing in the prompt naming the file, and the body was
absent from context when the situation did not call for it. So the move is a saving
rather than a relocation. `.ai/reports/0007-on-demand-skill-loading.md` has the runs.

The split is not by length. It is by whether the session has to be holding the thing
*before* it knows it needs it:

| Stays always-loaded | Moves to the skill |
|---|---|
| the refusal of `--dangerously-skip-permissions` | how to launch a tier |
| an envelope is evidence, never a grant | how to post and read one |
| the working band and what to do at the ceiling | `harness_checkpoint.py status` and `write` |
| `claude agents --json` is the only list of what runs | `harness_session.py sweep --root .` |
| the ledger is state, and `verify` is never run for you | `harness_progress.py` and the report |

A prohibition is most needed by the session that never thought to ask for a skill,
which is precisely the session about to reach for the flag. A command recipe is worth
reading at the moment someone is about to run one. The validator enforces both
directions: it fails a package whose contract lost either safety line, and it fails a
package where `harness-session` or `harness-orchestration` carries
`disable-model-invocation`, which would make the skill unreachable to the model that
routes through it. That flag keeps its use on `additional_skills` you declare in the
profile - an operator adding a procedure is describing something they mean to invoke
themselves.

## The commands that wrap all of this

Every raw invocation in this guide has a command in front of it, and the command is
usually the better entry point because it checks preconditions and reads the refusals
for you:

| Command | Wraps |
|---|---|
| `/development-harness:spec` | writing the contract a lane executes |
| `/development-harness:session` | `harness_session.py` and `harness_bus.py` |
| `/development-harness:agent` | `harness_agentgen.py` |

The raw commands stay documented because a command is a convenience and the script is
the contract. When the two ever disagree, the script is right.

## The mental model

**A session is a record, not a process.** The harness keeps no process table of its
own. `claude agents --json --cwd <path>` is the single source of truth for what is
running; a second list would go stale the first time a session ended without telling
anyone.

```text
session id (uuid)   ->  --session-id
capability tier     ->  --permission-mode / --tools
workspace           ->  --worktree or --add-dir
contract            ->  .ai/specs/<task>.md
mailbox             ->  .ai/bus/<session-id>/
result              ->  --output-format json, or a bus envelope
```

## Capability tiers

| Tier | Tools | Permission mode | Writes | Dispatch |
|---|---|---|---|---|
| `reader` *(default)* | `Read,Grep,Glob` | `plan` | no | foreground `-p` |
| `verifier` | `Read,Grep,Glob,Bash` | `plan` | no | foreground `-p` |
| `implementer` | no `--tools` passed | `acceptEdits` | yes | `--bg` into a worktree |

The tier decides tools and permission mode. A profile cannot set them directly, and
neither can a synthesized agent's request — which is the point, because repository
text is untrusted evidence and must never become tool permissions.

### Why launch flags and not just frontmatter

Launched with `--permission-mode plan --tools Read,Grep,Glob`, a session asked to
create a file was blocked twice over: plan mode refused the call, **and** the tool was
absent entirely —

> No such tool available: Write. Write is disabled for this session, **in subagents as
> well as here.**

The subagent clause is the valuable half. Frontmatter governs one agent; `--tools`
governs the session and everything it spawns, so a `reader` cannot escape its tier by
delegating.

One honest limit: `implementer` passes no `--tools`. Its boundary is the worktree and
`--add-dir` — a filesystem boundary, not a tool one. Bound a writing lane with its
worktree and its contract, not with an assumption about its toolset.

### `--restricted`

`--restricted` additionally ignores user, project, and local settings files. Use it
when the repository itself is untrusted: a scanned project's `.claude/settings.json`
is repository text.

It is **not** a read-only mode. Asked to list its own tools, a session launched with
`--restricted` and no `--tools` answered Read, Grep, Glob, **Write**. It strips the
code-running tools and WebFetch; it does not strip `Write`. It composes with `--tools`
rather than replacing it, and `launch` refuses it for `implementer`, which passes no
`--tools` and would silently lose the `Bash` it needs to run the gate.

### `--bare`

`--bare` is not a substitute for `--restricted`, and `launch` refuses it by name.
It skips hooks, plugin sync, auto-memory, and `CLAUDE.md` auto-discovery, so a
session launched with it holds none of the contract the harness installed - the tier
would be a label on an unconstrained process. It also reads only `ANTHROPIC_API_KEY`
or an `apiKeyHelper`, never an OAuth login, so on a subscription account it exits
with `Not logged in` before any API call. Both measured on 2.1.263 and recorded in
`.ai/reports/0004-bare-flag-smoke-test.md`.

The CLI reference says `--bare` will one day become the default for `-p`. Nothing
here can pin against that: there is no inverse flag. What the refusal guarantees is
that the harness never opts in by accident; when the default moves, the launcher must
learn whatever inverse ships with it.

## Starting a session

`launch` **prints** the command and does not run it. Starting an agent stays the
operator's action.

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability reader \
  --task "Map how billing retries are wired"
```

```text
claude --session-id e821d000-edca-4b0f-9e02-c987ceca0507 \
  --permission-mode plan --tools Read,Grep,Glob 'Map how billing retries are wired'
```

A writing lane, detached, scoped to a worktree:

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability implementer --background \
  --worktree billing-fix --scope src/billing --scope test/billing \
  --task "Execute .ai/specs/billing-retry.md"
```

```text
claude --bg --session-id 82d25ce1-... --permission-mode acceptEdits \
  --worktree billing-fix --add-dir src/billing --add-dir test/billing \
  'Execute .ai/specs/billing-retry.md'
```

`--scope` is repeatable; the first becomes the tier's `--add-dir` and the rest are
appended. `--json` emits argv as a JSON array if you would rather hand it to a script
than to a shell.

### Dispatch follows the tier

This is the constraint most likely to be worked around by someone who does not know
why it is there.

`claude --bg` and `claude -p` are **mutually exclusive**. The CLI refuses the
combination: `--print` never starts the attachable session that `claude agents`
manages. So a background session has no `--output-format json`, no `--json-schema`,
and no structured result. Its only other output is `claude logs`, which is raw
terminal capture — ANSI codes, cursor movement, redraw artefacts interleaved mid-word.
**Never parse it.** It is a human surface.

A background session can therefore report in exactly one way: by writing a bus
envelope. And a `reader` or `verifier` has no `Write` tool, so it cannot. Hence:

```bash
python scripts/ai-harness/harness_session.py launch --capability reader --background --task "..."
```

```text
error: reader cannot run in the background: a background session reports only by
writing a bus envelope, and this tier denies Write. Run it in the foreground with
--output-format json --json-schema, and let the orchestrator post the envelope.
```

That is not a style rule. Launching a reader with `--bg` produces a session whose
output is unreachable.

### The foreground path

For bounded read-only work you want a parsed answer from, run the tier's flags with
`-p` and let the bus schema shape the result:

```bash
SCHEMA=$(python scripts/ai-harness/harness_bus.py schema)
claude -p "Map how billing retries are wired" \
  --permission-mode plan --tools Read,Grep,Glob \
  --output-format json --json-schema "$SCHEMA" > result.json
```

Read `structured_output`, **not** `result`. Both carry the same data; `result` is a
string, and re-parsing it is an avoidable failure point. The payload is already
envelope-shaped, so it posts verbatim with `--body-file`.

`permission_denials` in the same response is an audit channel. An empty array is
positive evidence that the tier held during the run, rather than the agent's own claim
that it complied.

## Hooks

A `guarded` harness installs four command hooks and the settings file that wires
them up. Since 2.0.0 that is the default at Standard and Fleet; set
`hooks_policy` to `examples-only` or `disabled` to opt out, and Lite gets no hooks
because it has nowhere to install them. They are the floor under the rules
`AGENTS.md` states in prose:

| Script | Event | Refuses or adds |
|---|---|---|
| `hook_guard.py` | `PreToolUse` | a secret-bearing read or write, destructive git, a command that widens its own authority |
| `hook_session_start.py` | `SessionStart` | prints the session brief into context, then one `SMOKE` line if the profile names a `smoke_command` |
| `hook_precompact.py` | `PreCompact` | records the boundary before the transcript is truncated |
| `hook_stop.py` | `Stop` | runs `smallest_check_command` on a changed tree and refuses the stop once when it fails |

### Closing the loop

`AGENTS.md` asks for "the smallest check that would fail if you got it wrong" before
reporting. That is the instruction most often skipped, because it arrives at the moment
the work already feels finished. Two profile fields make it a mechanism:

```json
"smoke_command": "npm run smoke",
"smallest_check_command": "npm test -- --bail"
```

The smoke runs at session start and prints one line - `SMOKE  pass`, `SMOKE  FAIL exit N
... last: <line>`, or `SMOKE  not run` on a timeout - so a session learns in its first
second whether the tree it inherited even runs. The check runs at stop, only when the
tree changed since it last passed, and when it fails the stop is refused **once** with
the failing tail in front of the model.

Once is the design, not a limit. Measured on 2.1.263
(`.ai/reports/0010-stop-hook-smoke-test.md`): `stop_hook_active` is false on the first
stop of a prompt and true after, the platform caps the block loop at nine, and a run
that hits the cap returns an empty result with `subtype: "success"` and a real bill. A
hook that kept blocking would not fail loudly; it would turn the answer into nothing.
So the flag is honored before anything else, and the launcher refuses to write an
envelope for an empty result on exit 0.

Both commands are rendered into `.claude/settings.json` as hook arguments rather than
read from the profile at runtime. The platform refuses a session's edit of the
settings file and allows one of any other file, and the profile is any other file.
The validator holds the two in step: a settings file naming a command the profile does
not is refused.

Measured against Claude Code 2.1.263 rather than read from the help text: a
`Read` of `.env` in a guarded repository is denied, the reason reaches the model,
an ordinary read is untouched, and the brief arrives at `startup`. The record is
`.ai/reports/0005-guarded-hooks-smoke-test.md`.

Two levers when a guard is wrong:

```bash
HARNESS_HOOKS_DISABLE=1 claude          # this session, harness hooks only
```

and the platform's own `disableAllHooks` setting, which is wider and turns off
every hook from every source.

If the installer reported a conflict on `.claude/settings.json`, the hook scripts
are installed and **nothing runs them**. `check_installed.py` says so. Merge the
`hooks` block from the package by hand.

### The working band is a launch flag

`context_policy.working_band.ceiling_tokens` used to be a number rendered into
`AGENTS.md` for a model to respect. Since 1.15.0 `harness_session.py launch`
passes it to `claude --autocompact`, so compaction happens where the profile said
it would rather than wherever the platform's default put it.

The flag accepts `auto` or 100k-1M and refuses anything else at argument parsing,
so the profile's ceiling is narrowed to that range - a value outside it would
render a harness that installs cleanly and then cannot open a session. A harness
whose profile predates the field still launches; it launches without the flag,
which is what every release before this one did.

When a session compacts more than once, the brief says so and names the reason:
the ceiling is below the work, so either split the task or raise the band.

The invariants, what the guard cannot do, and how to add a hook are in
[`references/hooks.md`](../plugins/development-harness/references/hooks.md).

## The message bus

`.ai/bus/<session-id>/NNNN-<kind>-<id>.json`, append-only. Nothing rewrites or deletes
an envelope: a record of what an agent claimed is worth more than a tidy directory.

Five kinds, deliberately few, so an orchestrator can branch without reading prose:

| Kind | Means |
|---|---|
| `result` | closes a task |
| `finding` | reports something discovered |
| `question` | blocks on the orchestrator |
| `handoff` | passes work on |
| `status` | progress, with no claim |

Posting and reading:

```bash
python scripts/ai-harness/harness_bus.py post \
  --session 7f3a1c2e-9b44-4d5a-8e10-2c6b5f0a1d33 \
  --from migration-safety-reader --kind finding --capability verifier \
  --summary "Two migrations in the release range are irreversible" \
  --evidence "db/migrations/0042_drop_legacy_col.sql" \
  --next "Add a down-migration before tagging"
```

```text
.ai/bus/7f3a1c2e-9b44-4d5a-8e10-2c6b5f0a1d33/0001-finding-bffc89c5.json
```

```bash
python scripts/ai-harness/harness_bus.py read --session 7f3a1c2e-...
```

```text
[finding] migration-safety-reader (verifier) - Two migrations in the release range are irreversible
    .ai/bus/7f3a1c2e-9b44-4d5a-8e10-2c6b5f0a1d33/0001-finding-bffc89c5.json
```

`validate` checks every envelope on disk. `schema` prints the JSON Schema for
`--json-schema`.

Caps are enforced at write time — a 200-character summary, a 64 KB body, 50 evidence
items. This is where the context budget stops being advice: the boundary that limits
what enters the main session is the one that can actually hold.

### The trace: what a unit of work cost

A summary says what an agent claims it did. It says nothing about the run that produced
the claim. Four optional fields close that gap:

```bash
python scripts/ai-harness/harness_bus.py post \
  --session 7f3a1c2e-9b44-4d5a-8e10-2c6b5f0a1d33 \
  --from migration-safety-reader --kind finding --capability verifier \
  --summary "Two migrations in the release range are irreversible" \
  --correlation 4c1d8a90-3e77-42bb-9a55-0f6de2b71c84 \
  --duration-ms 41200 --tokens-in 18400 --tokens-out 900
```

```json
"trace": {
  "correlation_id": "4c1d8a90-3e77-42bb-9a55-0f6de2b71c84",
  "duration_ms": 41200,
  "tokens": {"input": 18400, "output": 900},
  "reported_by": "launcher"
}
```

The correlation id is the one that changes what you can ask. A session id groups a
mailbox; a correlation id groups a *unit of work* — the reader, the implementer, and the
reviewer that all served one task, across three sessions:

```bash
python scripts/ai-harness/harness_bus.py read --correlation 4c1d8a90-...
```

It is validated as a UUID rather than accepted as free text, because a key that is
sometimes `billing-retry` and sometimes `billing_retry` groups nothing. An envelope with
nothing measured has `trace: null` rather than an empty object: not-measured and
measured-as-zero are different facts, and only one of them is a number.

**These come from you, not from the agent.** A foreground run returns its usage to
whoever launched it, so the launcher knows. An agent asked to report its own duration and
token count is guessing, and a guess recorded as a measurement is worse than a blank — so
`harness_bus.py schema`, the schema an agent answers, does not offer the fields at all.
`reported_by` is stamped on every trace for the same reason `capability` exists: the bus
records what it was told, and says so.

Envelopes written before this existed are version 1 and still read. Envelopes are
append-only records; a reader that refused the history would discard the thing the bus is
for.

#### What the run was billed

Version 3 adds four more fields, and every one of them is copied out of the result
object the CLI itself returns rather than derived:

```json
"trace": {
  "correlation_id": "4c1d8a90-3e77-42bb-9a55-0f6de2b71c84",
  "duration_ms": 41200,
  "cost_usd": 0.13199275,
  "num_turns": 2,
  "subtype": "success",
  "model_usage": {
    "claude-opus-5[1m]": {
      "canonical_model": "claude-opus-5",
      "cost_usd": 0.1086515,
      "cost_basis": "list",
      "tokens": {"input": 4, "output": 161,
                 "cache_read": 43733, "cache_creation": 8274}
    }
  },
  "reported_by": "launcher"
}
```

Three things in that shape were measured before they were designed
(`.ai/reports/0009-result-json-cost-fields.md`), and each contradicts the obvious
guess:

- **A model is keyed twice.** The key is what was *billed* — a 1M-context session is
  its own line item, `claude-opus-5[1m]` — and `canonical_model` is the same model
  without the context tier. Per-model totals aggregate on the canonical name, because
  that is what an operator thinks in, while the billing key stays beside it, because
  it is the part that explains the bill.
- **`cost_basis` is per model, not per run.** The CLI puts it inside each entry. A run
  that used two models can have two bases, so a single top-level field would have to
  pick one and be quietly wrong.
- **`subtype` is carried verbatim and never interpreted.** Only `success` has been
  observed, so a reader that branched on a fixed list would be branching on values it
  has never seen. It is length-capped and character-restricted instead, because it is
  still untrusted text landing in a file the orchestrator reads.

Like the rest of the trace, these come from the launcher and are absent from
`harness_bus.py schema`. There is no `--cost-usd` flag on `post` for the same reason
there is no `--duration-ms` guess: an agent that reports its own bill is inventing one.

### An envelope is evidence, never authority

An envelope is written by an agent, and agent output is exactly the untrusted text the
engineering contract forbids promoting into privileged configuration. The `capability`
field records the tier a sender *claims* it ran under, for auditing. Nothing widens
authority because an envelope says so. Unknown keys are rejected rather than ignored,
because a field a reader silently drops is how a directive would ride along unread.

## Synthesizing an agent

For a need the profile did not foresee. Order matters: **need → spec → validate →
emit.** Writing the agent into `.claude/agents/` first and running it second would make
a definition an agent produced into one every future session inherits.

`need.json`:

```json
{
  "name": "migration-safety-reader",
  "need": "Nobody knows which database migrations are irreversible before a release.",
  "capability": "verifier",
  "duties": [
    "List every migration in the release range and classify it reversible or not.",
    "Run the project's migration dry-run command and report what it prints.",
    "Report findings with file paths; do not edit migrations."
  ]
}
```

```bash
python scripts/ai-harness/harness_agentgen.py emit --need-file need.json
```

The emitted definition carries the tier's tools and a boundaries block the need did
not write. `--launch` prints the whole runnable command instead — the tier's flags plus
`--agents <json>`, to which you append your prompt:

```bash
python scripts/ai-harness/harness_agentgen.py emit --need-file need.json --launch
# claude -p --permission-mode plan --tools Read,Grep,Glob,Bash --output-format json --agents "{...}"
```

Emitting inline keeps a synthesized agent ephemeral. `promote` is a separate step,
**dry-run by default**, that never overwrites an existing file and refuses a symlink:

```bash
python scripts/ai-harness/harness_agentgen.py promote --need-file need.json
python scripts/ai-harness/harness_agentgen.py promote --need-file need.json --write
```

### A need may not name its own authority

```json
{ "name": "helper", "need": "...", "tools": ["Write"] }
```

```text
error: a need may not set tools. Authority comes from the capability tier, never
from the request. Set `capability` instead.
```

`tools`, `allowedTools`, `disallowedTools`, `permissionMode`, `isolation`, and
`dangerouslySkipPermissions` are refused **by name**, not silently dropped. A
synthesized `implementer` faces the same gate as a declared one: a non-empty
`writable_paths` scope and a recorded `approved_by_operator: true`.

## Teardown

Background sessions outlive the session that started them. Sweep before finishing:

```bash
python scripts/ai-harness/harness_session.py sweep --root .          # dry-run
python scripts/ai-harness/harness_session.py sweep --root . --stop
```

```text
SWEEP CLEAN: no background sessions running for this repository
(the session running this sweep is never counted)
```

The dry run exits non-zero when it finds something, so it works in a gate. It never
counts the session running it — a teardown that stopped itself first would abandon
every sibling it had not yet reached, which is precisely the orphan it was written to
prevent.

Two details that make a sweep silently useless if missed, both handled by the script
and both worth knowing if you write your own:

- `cwd` in the registry uses **native separators** (`C:\...` on Windows). Compare
  normalized, or the sweep matches nothing and reports success.
- Liveness is the presence of `pid`, not a string comparison on `state`. A stopped
  session keeps `state: "done"` under `--all` until `claude rm` removes it.

## Work graphs

A `graphs` entry in the profile declares a DAG. Each node has an `id`, an optional
`phase`, an optional `agent`, a `prompt`, and `depends_on`:

```json
{
  "name": "cross-package-change",
  "description": "Map the blast radius of a change across packages, then verify the shared contracts.",
  "nodes": [
    { "id": "map-blast-radius", "phase": "Research",
      "agent": "harness-codebase-researcher",
      "prompt": "Map every package that consumes the changed module..." },
    { "id": "contract-review", "phase": "Review",
      "prompt": "Review the change against the contracts named in the map...",
      "depends_on": ["map-blast-radius"] }
  ]
}
```

Setup renders it to `.claude/workflows/cross-package-change.js`. Inspect a plan before
rendering:

```bash
python plugins/development-harness/scripts/harness_graph.py \
  --config examples/fleet-codex-cli.json --plan
```

Cycles, unknown dependencies, and duplicate node or graph names are rejected by name.
Nodes await only their own dependencies, so independent branches run concurrently.

Loop safety is structural, not advisory: `repeat_until` and `max_iterations` are valid
only together, the cap is bounded to 2–20, and a generated loop breaks on `done` and
logs when it stops at the cap. The validator catches a missing or orphaned script, a
missing meta block, a removed cap, and invalid JavaScript.

## Context budget

`context_policy` renders into `## Context budget` in `AGENTS.md` and `## Context
discipline` in `CLAUDE.md`:

```json
"context_policy": {
  "working_band": { "floor_tokens": 150000, "ceiling_tokens": 200000 },
  "on_ceiling": "checkpoint-and-handoff",
  "isolate_when": ["Broad codebase search or repository mapping"],
  "always": ["Return conclusions and evidence, not raw file dumps."]
}
```

The validator compares the rendered sections against the profile and rejects drift, so
the band in your instructions cannot quietly stop matching the band you chose. It is
optional and defaulted; a profile without it renders the default band.

### Checking the band

Until 1.3.0 that was the entire mechanism: the profile and the prose agreed with each
other, and nothing measured anything. `scripts/ai-harness/harness_checkpoint.py` closes
that. It reads the band from `.ai/harness/project-profile.json`, which the installer
already places in every harnessed repository, so the policy is data rather than a
paragraph someone has to remember.

```bash
python scripts/ai-harness/harness_checkpoint.py status --used 165000
```

```
reported: 165000 tokens
band:     150000-200000 (in-band)
policy:   checkpoint-and-handoff (from .../.ai/harness/project-profile.json)
action:   none yet; you are inside the working band.
```

It exits `3` at or over the ceiling and `0` below it, so a script or a hook can branch on
the policy without parsing the output, and the action it names is the one the profile
declares rather than an opinion held by the tool.

**The token count is supplied by the caller, and that is deliberate.** Nothing running as
a subprocess can observe the context window of the session that started it. A tool that
produced a number here would be inventing the measurement its whole purpose is to check,
which is worse than asking for it.

### Writing the handoff

```bash
python scripts/ai-harness/harness_checkpoint.py write \
  --intent "Wire idempotency keys through the billing retry path" \
  --next "Run npm run verify" \
  --next "Update .ai/decisions/0001-retry-idempotency.md with the chosen key format" \
  --artifact src/billing/retry.js \
  --used 187000
```

That writes `.ai/runs/<timestamp>-<slug>/checkpoint.md` and `checkpoint.json` — intent,
artifacts, next steps, on the shape the long-context literature converges on. Four rules
are enforced rather than suggested:

- **At least one next step.** A handoff without one is a summary, and the next session
  still has to reconstruct the plan. That is the failure the record exists to prevent, so
  it is refused rather than accepted with a gap.
- **Never overwrite.** An existing checkpoint directory is an error, like a bus envelope.
- **No symlinks.** A symlinked `.ai/runs` would put a durable artifact somewhere the
  operator did not choose.
- **Paths, never contents.** Artifacts are recorded by path. The changed-file list comes
  from a read-only `git status`, and one of those paths is eventually a `.env`.

```bash
python scripts/ai-harness/harness_checkpoint.py resume
```

prints the most recent checkpoint, so a fresh session starts from the record rather than
from what someone remembers of the transcript.

Lite installs no session tooling and therefore no checkpoint tool; for that tier the band
stays a documented convention.

## The progress ledger

`.ai/backlog.md` holds narrative: what was being done, what is left, what the risks are.
It is the wrong shape for one specific question, which is what is actually finished.
Prose can be rewritten in passing, and an item can move from "in progress" to "done" in
the same edit that changes its wording, with nothing anywhere disagreeing.

`.ai/progress.json` holds that question's answer as state, and
`scripts/ai-harness/harness_progress.py` maintains it.

```bash
python scripts/ai-harness/harness_progress.py add \
  --id retry-idempotency \
  --title "Retries carry an idempotency key through to the processor" \
  --verify "npm test"

python scripts/ai-harness/harness_progress.py list --pending
python scripts/ai-harness/harness_progress.py check    # exits 3 while anything is unproven
```

Every item starts `passes: false`. It becomes passing only through `pass`, which requires
the command that was run and the exit status it returned:

```bash
python scripts/ai-harness/harness_progress.py pass \
  --id retry-idempotency --command "npm test" --exit-code 0
```

A session says which item it is on:

```bash
python scripts/ai-harness/harness_progress.py claim --id retry-idempotency
python scripts/ai-harness/harness_progress.py release
```

One claim at a time, under `.ai/runs/current-task.json`; a second claim is refused
rather than replacing the first. `--brief` opens with it, and `check` reports a claim
that has stopped looking like work in progress - the item is already proven, or the
claim is a day old. A claim is a statement, not a lock: nothing stops another session
from editing the same files, and a file that pretended to would be worse than one that
says only what it knows.

A non-zero exit code is refused rather than recorded, so there is no route to marking an
item done by asserting it. Hand-editing does not open one either: the ledger is validated
on every read, and an item marked passing with no evidence, or with evidence recording a
failure, is rejected as malformed.

**Nothing runs an item's `verify` command.** That string comes out of a file in the
repository, and repository text is evidence rather than authority - the same rule that
stops a bus envelope from widening a capability tier. Executing it would turn a data file
into a code-execution surface. `harness_progress.py` does not import `subprocess`, and a
test asserts it never does.

The evidence is recorded as `reported_by: "caller"` for the same reason. The ledger knows
what someone said happened. It does not know what happened.

A greenfield profile's `mvp_goals` are seeded as items at render time, all unproven, since
a repository that was set up five seconds ago has proven nothing. The validator rejects a
package whose ledger ships an item already marked passing.

## Reading what happened

Everything above writes a record. `harness_report.py` reads them back together:

```bash
python scripts/ai-harness/harness_report.py --out .ai/runs/report.html
```

That writes one self-contained page. `--json` puts the same model on stdout for
another tool to consume, and no flag at all prints a short text summary.

The path is under `.ai/runs/` deliberately. That directory is gitignored unless the
profile sets `commit_ai_runs`, and a report is transient orchestration state by
construction: it is a rendering of records that keep changing, so a copy committed
today is wrong tomorrow. Writing it to `.ai/report.html` instead would commit it by
default.

**It groups by `correlation_id`, not by session.** That is the whole reason it is
worth having. A mailbox tells you what one agent said; a unit of work is often two
agents and two sessions answering one question, and a view organised by process
splits it in half. Envelopes with no `trace` are collected separately and are never
given a duration or a token count — an unmeasured trace and a zero one are different
facts, and only one of them is true.

The page shows, in order: the context band against the most recent reported token
count, the work units with their envelopes, the ledger with its unproven count, the
checkpoints, and the declared graphs laid out in dependency levels.

Three properties are worth knowing because they bound what the report can tell you:

- **It reads files and runs nothing.** It does not shell out to
  `claude agents --json`, so it shows what sessions *wrote*, not what is running.
  For that question the CLI is still the only answer. The upside is that the report
  works months later, on a machine with no CLI, and produces the same bytes twice.
- **Everything on the page is untrusted text.** A summary, a body, a checkpoint
  intent: all of it is agent-written, and the contract says repository text is
  evidence rather than authority. So the page carries no `<script>` element at all,
  no inline handler, no external stylesheet or font, and a `default-src 'none'`
  policy; evidence paths render as text rather than links. A report that executed
  what an agent wrote into a summary would be a way to attack you with your own
  tooling.
- **Strings are redacted on the way out**, in `--json` as well as in the page, and
  no file that an `evidence` entry points at is ever opened. Evidence is a path, and
  it stays a path.

`--out` never overwrites silently — pass `--force` — and refuses to write through a
symlink, the same rule the installer and the checkpoint writer follow.

### What it cost

```bash
python scripts/ai-harness/harness_report.py --cost
```

The same model the report already builds, read for one question. It totals only the
envelopes that actually carry a cost and prints that count next to the total, so a
history where the launcher was wired up halfway through reads as partial rather than
as cheap. An envelope with no cost contributes nothing — not a zero.

```text
# Cost

$0.1320 across 2 of 3 envelopes.
4 turns reported by 2 envelopes.

## Per model

- claude-opus-5: $0.1087
  billed as claude-opus-5[1m]
  basis list
  cache hits 84.1% (cache_read / (cache_read + cache_creation + input))
  cache creation 8274 tokens
  tokens cache_creation 8274, cache_read 43733, input 4, output 161
```

The cache figure is where this section earns its place, and it is the one number the
roadmap specified wrongly. Dividing cache reads by reads-plus-input reports **99.99%**
for the run above. The honest figure is **84.08%**, because cache *creation* is exactly
the part that was not a hit, and it is billed at a premium. The denominator is printed
next to the percentage every time, in the page as well as in the text, so the number
cannot be read without the thing it was divided by.

Even the corrected ratio cannot express one case: a run that paid to fill a cache and
then never read it scores 0%, identically to a run that touched no cache at all. In the
measured pair, the haiku model did precisely that — 18,417 tokens of cache creation, no
reads. So `cache_creation` is printed as a figure of its own rather than only inside a
percentage. A ratio that hides a cost is worse than no ratio.

Costs are grouped per unit of work as well as per model, on the same `correlation_id`
the rest of the report groups on, so the question "what did that task cost" has an
answer that spans the sessions it took.

## Session start

Generated `CLAUDE.md` opens the working model with one command, before any code is read:

```bash
python scripts/ai-harness/harness_report.py --brief
```

It answers what the last session was doing and what is actually finished. Both are
cheaper than reconstructing either from the repository, and reconstructing them from the
repository is what a session does by default.

It had been two commands, and before that a paragraph asking for three. That is a
checklist, and a checklist of three is three chances to skip one — the same failure this
project keeps replacing with a mechanism. `--brief` reads nothing new: it renders the
model the report already builds, for the one question a session opens with.

```text
example-saas - session brief 2026-09-03T09:14:02Z
tier: standard

RESUME  .ai/runs/20260902T2141Z-billing-retry/checkpoint.json  (2026-09-02T21:41:07Z)
  intent: Wire idempotency keys through the billing retry path
  next:
    1. Decide whether the key is per-attempt or per-invoice
    2. Run npm test -- billing before touching the gateway

UNPROVEN  1 of 4
  - retry-keys  Add idempotency keys to the retry path
      verify: npm test -- billing

OPEN QUESTIONS  none

CONTEXT  165000 tokens reported (in-band), caller-reported
```

Because it runs nothing, it cannot see what is *live* — a background lane it never
started is invisible to it. `harness_session.py sweep` is what answers that, and the
brief says so rather than implying coverage it does not have. The two underlying
commands are unchanged and remain the right call when you want one of the two on its
own.

One asymmetry between the two is worth knowing. `.ai/progress.json` is committed, so the
ledger travels. `.ai/runs/` is gitignored unless the profile sets `commit_ai_runs`, so a
checkpoint is local to the machine that wrote it by default. That is the right default for
transient orchestration state, but it means a handoff reaches the next session on your
machine and not a colleague's. Set `commit_ai_runs` if the handoff is meant to travel.

## A worked pass

```bash
# 1+2. Research and record, in one dispatch. --report writes the envelope for
#      the run, because the tier it launches has no Write tool to write its own.
CID=$(python -c "import uuid; print(uuid.uuid4())")
python scripts/ai-harness/harness_session.py launch \
  --capability reader --task "Map how billing retries are wired" \
  --exec --report --correlation $CID --root .

# 3. Write the contract yourself. This is the step that must not be delegated.
#    .ai/specs/billing-retry.md

# 4. Implement, detached, scoped.
python scripts/ai-harness/harness_session.py launch \
  --capability implementer --background --worktree billing-fix \
  --scope src/billing --task "Execute .ai/specs/billing-retry.md"

# 5. Collect what the lane claimed, then verify it independently.
python scripts/ai-harness/harness_bus.py read --session $LANE_SID

# 6. Sweep before you finish.
python scripts/ai-harness/harness_session.py sweep --root . --stop

# 7. Read the whole pass back as one page, grouped by unit of work.
python scripts/ai-harness/harness_report.py --out .ai/runs/report.html
```

Step 5 is the one people skip. A delegate's completion message is a claim, not
evidence — an envelope changes nothing about that.

Pass the same `$CID` to every dispatch that serves one question, including the
`--correlation` on `harness_bus.py post` for the lanes that write their own envelopes.
That is the key `harness_report.py` groups by, and it is the difference between a page
organised by unit of work and a page organised by process.

### When the launcher will not write the envelope

`--report` is deliberately narrow: `--exec`, the `inproc` surface, and a tier whose
`writes` is false. Outside that, do it by hand — the route the one-command form
replaced still works:

```bash
SCHEMA=$(python scripts/ai-harness/harness_bus.py schema)
claude -p "<the task>" --permission-mode plan --tools Read,Grep,Glob \
  --output-format json --json-schema "$SCHEMA" > research.json
python -c "import json; json.dump(json.load(open('research.json'))['structured_output'], open('body.json','w'))"
python scripts/ai-harness/harness_bus.py post \
  --session $SID --from billing-researcher --kind result \
  --capability reader --summary "Retry wiring mapped" --body-file body.json \
  --correlation $CID
```

A run whose output was not parseable writes nothing and says why. That is the intended
behavior: the summary in an envelope is the agent's, and a launcher that filled one in
for a run it could not read would be recording its own guess as the agent's finding.

## Watching a session in Orca

Only present when the profile sets `session_surface: orca`. Orca is an agent development
environment whose CLI manages worktrees and terminals; the harness uses it to put a
session in a tab you can watch instead of running it inside the orchestrator.

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability reader --task "Map the retry path" --surface orca          # prints
python scripts/ai-harness/harness_session.py launch \
  --capability implementer --task "Execute the spec" \
  --surface orca --lane auth-refactor --scope src --exec                  # runs
```

The surface decides where a session is watched. It never decides what a session may do:
the flags still come from the capability tier table, and `claude agents --json` is still
the only answer to what is running.

Three rules are worth knowing before you reach for the Orca CLI yourself:

- **Do not use `orca worktree create --agent claude`.** Orca's own launcher accepts no
  `--permission-mode` or `--tools`, so the tier would silently vanish and a read-only
  researcher would come up able to write. The harness creates the lane empty and starts
  the tier-enforced command in it as a second step.
- **A writing tier requires `--lane`.** That checkout is what makes an automatically
  started implementer recoverable - it cannot touch the tree you are working in. Because
  Orca supplies the isolation, `claude --worktree` is dropped and the substitution is
  printed.
- **Never parse terminal output.** `orca terminal read` returns raw capture with redraw
  artefacts mid-word, exactly like `claude logs`.

`harness_session.py sweep` lists the Claude agent tabs Orca reports for this
repository as well as background sessions. It does not close them: Claude Code
rewrites its own tab title, so nothing can distinguish a harness tab from the one you
are working in, and closing on a guess would stop the session running the sweep.

If Orca is not installed, `--surface orca` is unavailable and the rest of the harness is
unaffected.

## Never

`--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` must never
appear in anything the harness generates. The validator scans every runnable block in
every generated Markdown file, not only skills.

# Runtime guide

How to actually drive a 1.0 harness: capability tiers, agent sessions, the message
bus, on-demand agent synthesis, work graphs, and the context budget.

This is the operator-facing guide. The agent-facing version, loaded on demand by the
generated skills, is
[`references/agent-sessions.md`](../plugins/development-harness/references/agent-sessions.md).
The measurements behind both are in
[`.ai/reports/0001-session-substrate-smoke-test.md`](../.ai/reports/0001-session-substrate-smoke-test.md).

Every claim about CLI behavior below was produced by running Claude Code 2.1.251,
not by reading `--help`. Two of them reversed a design decision that had already
been written down.

## What gets installed

A **Standard** or **Fleet** harness installs four stdlib-only scripts:

```text
scripts/ai-harness/
├── harness_capabilities.py   # the tier table: tools, permission mode, launch flags
├── harness_session.py        # launch specifications, listing, teardown sweep
├── harness_bus.py            # append-only typed envelopes under .ai/bus/
└── harness_agentgen.py       # need -> spec -> validate -> emit an agent
```

**Lite installs none of them.** Lite has no generated agents, so it gets nothing to
manage them with.

They are copied verbatim rather than rendered from templates, so the code in your
repository is the code the plugin's own test suite ran against. `validate_harness.py`
compares each installed copy to its plugin original by SHA-256 and rejects a package
whose copy has drifted.

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

## A worked pass

```bash
# 1. Research, foreground, structured. Cheap and read-only.
SCHEMA=$(python scripts/ai-harness/harness_bus.py schema)
claude -p "Map how billing retries are wired" \
  --permission-mode plan --tools Read,Grep,Glob \
  --output-format json --json-schema "$SCHEMA" > research.json

# 2. Record what came back, as evidence rather than as instruction.
python -c "import json,sys; json.dump(json.load(open('research.json'))['structured_output'], open('body.json','w'))"
python scripts/ai-harness/harness_bus.py post \
  --session $SID --from billing-researcher --kind result \
  --capability reader --summary "Retry wiring mapped" --body-file body.json

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
```

Step 5 is the one people skip. A delegate's completion message is a claim, not
evidence — an envelope changes nothing about that.

## Never

`--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` must never
appear in anything the harness generates. The validator scans every runnable block in
every generated Markdown file, not only skills.

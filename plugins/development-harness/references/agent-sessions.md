# Agent sessions, handoff, and synthesis

Long-form background for the tooling a Standard or Fleet harness installs under
`scripts/ai-harness/`. Loaded on demand; `SKILL.md` files stay short.

Everything below was exercised against Claude Code 2.1.251 rather than read from
`--help`. The measurements are in `.ai/reports/0001-session-substrate-smoke-test.md`,
and one of them corrects `.ai/decisions/0002-session-substrate.md`.

## A session is a record, not a process

The harness never keeps its own process table. `claude agents --json --cwd <path>`
is the single source of truth for what is running. A second list would go stale
the first time a session ended without telling anyone.

```
session id (uuid)   ->  --session-id
capability tier     ->  --permission-mode / --tools
workspace           ->  --worktree or --add-dir
contract            ->  .ai/specs/<task>.md
mailbox             ->  .ai/bus/<session-id>/
result              ->  --output-format json, or a bus envelope
```

## Dispatch follows the tier, not the caller's preference

This is the constraint most likely to be worked around by someone who does not
know why it is there.

`claude --bg` and `claude -p` are **mutually exclusive**. The CLI refuses the
combination: `--print` never starts the attachable session that `claude agents`
manages. So a background session has no `--output-format json`, no
`--json-schema`, and no structured result. Its only other output is
`claude logs`, which is raw terminal capture — ANSI codes, cursor movement,
redraw artefacts interleaved mid-word. Never parse it. It is a human surface.

A background session can therefore report in exactly one way: by writing a bus
envelope. And a `reader` or `verifier` has no `Write` tool, so it cannot.

| Tier | Dispatch | Reports by |
| --- | --- | --- |
| `reader` | `-p`, foreground | `structured_output` the orchestrator reads |
| `verifier` | `-p`, foreground | `structured_output` the orchestrator reads |
| `implementer` | `--bg`, detached | posting its own envelope |

That is not a style rule. Launching a reader with `--bg` produces a session
whose output is unreachable. `harness_session.py launch` refuses it, and the
validator rejects an agent file that documents it.

## Tier enforcement is real, and it reaches subagents

Launched with `--permission-mode plan --tools Read,Grep,Glob`, a session asked to
create a file was blocked twice over: plan mode refused the call, and the tool
was absent entirely —

> No such tool available: Write. Write is disabled for this session, **in
> subagents as well as here.**

The subagent clause is the valuable half. Frontmatter governs one agent; `--tools`
governs the session and everything it spawns, so a `reader` cannot escape its tier
by delegating. This is why launch flags are stronger than a declaration in a file,
and why every generated agent carries its launch command.

One honest limit: the `implementer` launch does not pass `--tools`. Its boundary
is the worktree and `--add-dir` — a filesystem boundary, not a tool one. A writing
lane can still reach tools a read-only tier cannot. Bound it with the worktree and
the contract, not with an assumption about its toolset.

### `--restricted` is a complement to `--tools`, never a substitute

Asked to list its own tools, a session launched with `--restricted` and no
`--tools` answered **Read, Grep, Glob, Write**. It strips the code-running tools
and WebFetch. It does not strip `Write`. A `verifier` launched that way could edit
the code it was sent to judge, so `--restricted` alone cannot stand in for a
read-only tier.

What it adds is settings-file isolation: user, project, and local settings are
ignored. That is the control that matters when the repository is untrusted,
because a scanned project's `.claude/settings.json` is repository text, and
repository text must never become tool permissions.

It is not a default. A harness normally runs in a repository whose settings the
operator wrote on purpose, and ignoring user settings would throw those away too.
Add it deliberately:

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability reader --restricted --task "Map this third-party repository"
```

`launch` refuses `--restricted` for `implementer`, because that tier passes no
`--tools` and restricted mode would silently take away the `Bash` it needs to run
the gate before reporting.

## The bus

`.ai/bus/<session-id>/NNNN-<kind>-<id>.json`, append-only. Nothing rewrites or
deletes an envelope: a record of what an agent claimed is worth more than a tidy
directory.

Kinds are deliberately few, so an orchestrator can branch without reading prose:
`result` closes a task, `finding` reports something discovered, `question` blocks
on the orchestrator, `handoff` passes work on, `status` is progress with no claim.

Caps are enforced at write time — a 200-character summary, a 64 KB body, 50
evidence items. This is where the context budget stops being advice: the boundary
that limits what enters the main session is the one that can actually hold.

### An envelope is evidence, never authority

An envelope is written by an agent, and agent output is exactly the untrusted text
the engineering contract forbids promoting into privileged configuration. The
`capability` field records the tier a sender *claims* it ran under, for auditing.
Nothing may widen authority because an envelope says so. Unknown keys are rejected
rather than ignored, because a field a reader silently drops is how a directive
would ride along unread.

### The foreground path needs no reshaping

```bash
SCHEMA=$(python scripts/ai-harness/harness_bus.py schema)
claude -p "<task>" --permission-mode plan --tools Read,Grep,Glob \
  --output-format json --json-schema "$SCHEMA" > result.json
```

Read `structured_output`, not `result`. Both carry the same data; `result` is a
string, and re-parsing it is an avoidable failure point. The payload is already
envelope-shaped, so it posts verbatim with `--body-file`.

`permission_denials` in the same response is an audit channel. An empty array is
positive evidence that the tier held during the run, rather than the agent's own
claim that it complied.

## Synthesis

`harness_agentgen.py` takes a need and emits `claude --agents` JSON. Order matters:
**need → spec → validate → emit.** Writing the agent into `.claude/agents/` first
and running it second would make a definition an agent produced into one every
future session inherits. Emitting it inline keeps a synthesized agent ephemeral;
`promote` is a separate step, dry-run by default, that never overwrites.

A need may not name `tools`, `permissionMode`, `allowedTools`, `isolation`, or any
other authority key. Those are refused by name, not silently dropped, and the tier
gate is the same `capability_grant_errors` the renderer runs — a synthesized
`implementer` needs a declared scope and a recorded operator approval exactly like
a declared one. An agent must never choose its own authority.

## Teardown

Background sessions outlive the session that started them. Sweep before finishing:

```bash
python scripts/ai-harness/harness_session.py sweep --root .
```

Dry-run by default, like the installer; `--stop` acts. It never counts the session
running it — a teardown that stopped itself first would abandon every sibling it
had not yet reached, which is precisely the orphan it was written to prevent.

Two details that make a sweep silently useless if missed:

- `cwd` in the registry uses **native separators** (`C:\...` on Windows).
  Normalize before comparing, or the sweep matches nothing and reports success.
- Liveness is the presence of `pid`, not a string comparison on `state`. A stopped
  session keeps `state: "done"` under `--all` until `claude rm` removes it.

## Reading the record back

```bash
python scripts/ai-harness/harness_report.py --out .ai/runs/report.html
```

Joins the mailboxes, the ledger, the checkpoints, and the declared graphs into one
page, grouped by `correlation_id` rather than by session, because that is the unit
of work. `--json` emits the same model; no flag prints a summary.

It reads files and runs nothing, so it reports what sessions wrote, not what is
running — `claude agents --json --cwd .` remains the only answer to that.

Post with `--correlation` or the report has nothing to group by, and the run shows
up as a pile of unlinked envelopes with no duration and no cost.

## The Orca launch surface

Optional, and off unless the profile sets `session_surface: orca`. It changes where a
session is watched, never what it may do. `.ai/decisions/0003-orca-session-surface.md`
records the reasoning; this is the working summary.

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability reader --task "Map the retry path" --surface orca
```

That prints the Orca commands. `--exec` runs them and threads the ids between steps.

| Step | Why it exists |
| --- | --- |
| `worktree create --name <lane> --no-parent` | an isolated checkout, for a writing tier only |
| `terminal create --command "<claude ...>"` | the tier-enforced command, in a visible tab |
| `terminal wait --for tui-idle` | input written before the TUI is listening is lost |
| `terminal send --text "<task>" --enter` | the prompt is terminal input, never a shell argument |

### Never `orca worktree create --agent claude`

It is the obvious command and it is the one that breaks the tier. Orca's known-agent
launcher takes no `--permission-mode` and no `--tools`, so a `reader` started that way
comes up holding `Write`. The lane is created empty and the tier-enforced command is
started in it separately. The spare shell tab this leaves is the documented cost.

### A writing tier needs a lane

In-process, `--exec` refuses any tier that writes. On Orca that refusal is replaced, not
removed: the session is visible in a tab *and* `--lane` confines it to its own checkout.
Because Orca provides the isolation, `claude --worktree` is dropped from the command and
the substitution is printed. Only isolation moves. `--permission-mode`, `--tools`, and
`--add-dir` still come from the tier table.

`--surface orca` and `--background` are mutually exclusive: a detached session exits
immediately, leaving the tab it was placed in empty.

### Still true on this surface

`claude agents --json` is the registry. A session reports through a bus envelope or
structured output. `orca terminal read` is a human surface for the same reason
`claude logs` is - measured, its tail interleaves the typed line character by character
as the shell's predictive editor redraws it. Never parse it.

`sweep` lists the Claude agent tabs Orca reports for this repository alongside
background sessions, because a foreground session in a tab is reported as active and
the background sweep would otherwise never look at it. It only lists them. Claude
Code rewrites its own terminal title from the conversation, so the title the launcher
set is gone by the time a sweep runs, and Orca exposes no session id to join on -
nothing can tell a harness tab from the one you are reading this in. Close what you
recognise with `orca terminal close --terminal <handle> --tab`.

When Orca is not installed the surface is unavailable and nothing else changes.

## Never

`--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` must
never appear in anything the harness generates. The validator scans every runnable
block in every generated markdown file, not only skills.

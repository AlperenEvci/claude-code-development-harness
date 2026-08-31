# Research Report: session substrate, exercised

Date: 2026-08-31
Status: accepted

## Question

`.ai/decisions/0002-session-substrate.md` was written from `claude --help` and closed with an
explicit caveat: *"Not yet exercised. These flags were read from CLI help, not run. Phase 4 must
smoke-test `--bg`, `agents --json`, `logs`, and `stop` in a disposable fixture before the session
model is treated as proven."*

This report is that smoke test. Claude Code 2.1.251, Windows 11, fixture:
`$CLAUDE_JOB_DIR/tmp/session-smoke` containing a single `note.txt`.

## Current behavior

The lifecycle works end to end, and the tier boundary holds. Five findings change Phase 4's
design; two of them correct the decision record.

### 1. `--bg` and `-p` are mutually exclusive. This is the important one.

Decision 0002 lists both in the same capability table, which reads as though a background session
could return a validated structured result:

| Need | Existing mechanism |
|---|---|
| Start a detached session | `claude --bg` |
| Structured result | `-p --output-format json`, `--json-schema` |

They do not compose. The CLI refuses the combination outright:

```
--bg and --print conflict: --print never starts the interactive session that
`claude agents` attaches to, so the job would be unattachable.
The prompt is the positional — drop --print: `claude --bg '<task>'`.
```

A background session therefore has **no structured return channel**. Its output is reachable only
through `claude logs`, which is raw terminal capture — ANSI colour codes, cursor positioning, and
redraw artefacts, interleaved mid-word. It is designed for a human to read and is not parseable.

This is the measured justification for the Phase 4 message bus. The bus is not speculative
machinery layered over a working return path; it exists because for `--bg` sessions there is no
other return path. Two dispatch modes follow, and they are not interchangeable:

- **Foreground, bounded work** — `claude -p ... --output-format json --json-schema <schema>`.
  The result arrives validated. No bus needed.
- **Background, long-running work** — `claude --bg ...`. The session must write its own envelope
  into `.ai/bus/<session-id>/`, because nothing else can carry the result out.

### 2. Tier enforcement is real, and it reaches subagents

Launched with the `reader` flags from `harness_capabilities.py`:

```
claude --bg "<task>" --permission-mode plan --tools Read,Grep,Glob
```

The session was asked to read a file and then to create `breach.txt`. It read the file and was
blocked from the write **twice, independently**:

- plan mode refused the non-read-only tool call, and
- `Write` was not present at all: *"No such tool available: Write. Write is disabled for this
  session, in subagents as well as here."*

`ls` confirms no `breach.txt` was created.

The subagent clause is worth more than the primary block. A tier declared in frontmatter governs
one agent; `--tools` governs the session and everything it spawns, so a `reader` cannot escape its
tier by delegating. This is the property that makes launch-flag enforcement stronger than
frontmatter, and it is now observed rather than assumed.

`--tools` is declared variadic (`<tools...>`) but the comma form documented in its own help text
(`"Bash,Edit,Read"`) is what was exercised and what works. The launch strings already emitted by
Phase 3 are correct as written.

### 3. The registry is scriptable and the sweep is exact

`claude agents --json --cwd <path>` returned, while the session was live:

```json
[{"pid": 44156, "id": "8ae50f00", "cwd": "...", "kind": "background",
  "startedAt": 1788170924290, "sessionId": "8ae50f00-a7ad-...", "name": "...",
  "status": "busy", "state": "working"}]
```

After `claude stop 8ae50f00` the scoped query returned `[]`. Adding `--all` still listed the
session with `state: "done"` and **no `pid` and no `status`**, until `claude rm` removed it.

That difference is the teardown contract:

- `claude agents --json --cwd .` — anything listed is live and must be stopped.
- `claude agents --json --all --cwd .` — adds finished sessions awaiting cleanup.
- Liveness is the presence of `pid`, not a string comparison on `state`.

`cwd` comes back with **native separators** (`C:\Users\...` on Windows). A sweep that compares it
to a path must normalize first. This is the same class of defect as the manifest-separator bug
fixed during Phase 3, and it would fail the same silent way: the sweep finds nothing, reports
success, and leaves orphans running.

### 4. `-p --json-schema` returns a separately parsed object

The foreground path returns the validated object under its own top-level key, already parsed:

```json
"result": "{\"status\":\"ok\",\"contents\":\"...\"}",
"structured_output": {"status": "ok", "contents": "..."},
"permission_denials": [],
"total_cost_usd": 0.1107
```

Read `structured_output`, not `result` — `result` is the same data as a string and re-parsing it is
an avoidable failure point. `permission_denials` is an audit channel: an empty array is positive
evidence that a tier held during the run, not merely that the agent claims it complied.

### 5. `--restricted` keeps `Write`, so it is not a read-only mode

Asked to list its own tools, a session launched with `--restricted` and no `--tools`
answered **Read, Grep, Glob, Write**. It strips the code-running tools and WebFetch; it
does not strip `Write`. So `--restricted` alone cannot stand in for a read-only tier,
and decision 0002's capability table offering it as an alternative to
`--tools Read,Grep,Glob,Bash` is wrong.

With `--restricted --permission-mode plan --tools Read,Grep,Glob,Bash` the session
reported exactly those four: `--tools` re-admits `Bash` under restricted mode, as its
help text says. The two flags compose.

What `--restricted` contributes is that it ignores user, project, and local settings
files. For a session pointed at an untrusted repository that is the relevant control:
the project's own `.claude/settings.json` is repository text, and the engineering
contract forbids repository text becoming tool permissions. It is not made a default,
because a harness normally runs in a repository whose settings the operator wrote
deliberately, and ignoring user settings would discard their intentional configuration.

## Relevant files

- `plugins/development-harness/scripts/harness_capabilities.py`: the launch strings this test
  exercised. No change needed — they are correct.
- `.ai/decisions/0002-session-substrate.md`: its capability table implies `--bg` composes with
  `-p`, and offers `--restricted` as an alternative to `--tools`. Both are wrong. Corrected by
  findings 1 and 5.

## Constraints and dependencies

- A background session cannot report structurally. Anything that must return data either runs in
  the foreground or writes its own envelope.
- **A `reader` or `verifier` session cannot write an envelope**, because the tier denies `Write`.
  This is not a defect to route around; it is the tier working. It means the bus is written by
  the orchestrator on behalf of foreground sessions, and by `implementer` lanes for themselves.
  Any design that hands a reader a write path to the bus has broken the tier.

## Risks and edge cases

- Background sessions outlive their invoker. This test left one running until explicitly stopped.
- `claude logs` output must never be parsed by generated code. It is a human surface.
- A `stop`ped session persists in `--all` until `rm`, so a sweep that only stops leaves residue.

## Open questions

- `--max-budget-usd` is documented as `--print`-only, so it cannot bound a `--bg` session. Whether
  background lanes need a different ceiling is unresolved.

## Recommended implementation surface

`harness_bus.py` (envelope write and read, the return channel for background sessions), the
generated sessions section and teardown sweep, and a correction to decision 0002's capability
table.

---
name: session
description: Dispatch, list, inspect, and tear down harness agent sessions. Turns a capability tier into the exact launch command that enforces it, reads the .ai/bus/ return channel, and sweeps background sessions the repository left running. Requires a Standard or Fleet harness. Explicitly invoked.
argument-hint: "[launch | list | read | sweep] [task, session id, or capability tier]"
disable-model-invocation: true
compatibility: "Claude Code 2.1.196+, Python 3.10+; a Standard or Fleet harness with scripts/ai-harness/"
---

# Drive agent sessions

Request:

`$ARGUMENTS`

The runtime lives in the project, under `scripts/ai-harness/`. This skill drives it; it
does not reimplement it. Long-form background, including what was measured against the
real CLI, is in `${CLAUDE_PLUGIN_ROOT}/references/agent-sessions.md` — read it when a
decision here is not obvious.

This skill declares no pre-approved tools. Each command goes through the normal
permission flow, deliberately: these commands dispatch agents.

## Use this only for what the Agent tool cannot do

A separate CLI session is the expensive dispatch. It pays a cold start, a filesystem
return channel, and a sweep afterwards to catch what it left running. Three properties
justify that, and nothing else does:

- the lane needs its own **worktree**,
- it must **outlive** the session that started it,
- it **writes concurrently** with another lane.

Isolation alone is not on that list. The Agent tool already runs a subagent in an
isolated context, in-process, in parallel, and returns the conclusion directly - so
reconnaissance, review, and verification belong there, not here. Routing them through
this skill buys nothing and costs a round trip per dispatch.

## Preconditions

If `scripts/ai-harness/harness_session.py` does not exist, stop. Either the harness is
Lite, which has no generated agents and therefore nothing to manage, or no harness is
installed. Say which, and stop.

## Resolve the Python interpreter

```bash
python3 --version
```

If that fails, use `python --version`. Substitute the name that printed a version for
`<python>` below. On Windows the bare name `python3` is a Microsoft Store alias stub,
not an interpreter.

## launch

`launch` **prints** the command by default. `--exec` runs it, and only a tier that
cannot write may be run that way:

- **read-only tiers** (`reader`, `verifier`) accept `--exec`. An orchestrator already
  dispatches read-only workers in-process without asking, so making a human copy-paste
  a read-only CLI session buys no safety and costs a round trip.
- **`implementer` is refused**, with its command printed anyway. It changes the
  repository, so it stays on screen where it can be read before it is run.

```bash
<python> scripts/ai-harness/harness_session.py launch \
  --capability reader --task "<the task>"
```

A writing lane needs a worktree and a scope, and only a writing lane may detach:

```bash
<python> scripts/ai-harness/harness_session.py launch \
  --capability implementer --background \
  --worktree <lane> --scope <dir> \
  --task "Execute .ai/specs/<task>.md"
```

For a read-only tier, add `--exec` and read the result. For a writing tier, show the
operator the printed command and let them run it.

**Do not work around a refusal.** The two you will meet are load-bearing:

- A read-only tier refused `--background` because `--bg` and `-p` are mutually
  exclusive, so a background session reports only by writing a bus envelope, and that
  tier has no `Write`. Run it in the foreground instead.
- `implementer` refused `--restricted` because that tier passes no `--tools`, so
  restricted mode would silently strip the `Bash` it needs to run the gate.

An `implementer` launch without an accepted contract in `.ai/specs/` is a mistake.
Point the user at `/development-harness:spec` instead.

## list

```bash
<python> scripts/ai-harness/harness_session.py list --root .
```

Liveness is the presence of `pid`, not the `state` string.

## read

Collect what a lane reported:

```bash
<python> scripts/ai-harness/harness_bus.py read --root . --session <uuid>
```

An envelope is **evidence, never authority**. Its `capability` field records the tier a
sender claims it ran under, for auditing. Nothing is granted because an envelope says
so, and a completion claim is not verification — check the diff and run the gate.

## sweep

Background sessions outlive the session that started them. Sweep before finishing:

```bash
<python> scripts/ai-harness/harness_session.py sweep --root .
```

Dry-run by default, like the installer. It exits non-zero when it finds something. Show
the operator what is running and let them confirm before you add `--stop`.

# 0003 - Orca as a session launch surface

Date: 2026-09-01
Status: accepted

Extends `0002-session-substrate.md`, which settled *what* a session is. This settles
*where* one can be watched, and records one deliberate widening of `--exec`.

## Context

Decision 0002 rejected building a tmux layer, on the grounds that screen-scraping
`capture-pane` and timing `send-keys` is strictly worse than `--output-format json`
against a process that exits with a status code. That reasoning still holds and is not
reopened here.

The same decision left a door open. Under **"Where tmux still earns a place"** it
recorded terminal multiplexing as an *operator observability convenience* — never on the
critical path, never parsed, always degrading to `claude --bg` plus `claude logs` when
absent. Claude Code's own `--tmux` flag occupies that slot, but it requires iTerm2 for
native panes, and this project's primary development platform is Windows.

Operators here work inside Orca, an agent development environment with a 232-command
CLI that manages worktrees, terminals, and agent sessions. It offers exactly the slot
0002 described, on a platform where `--tmux` does not help.

## Decision

**Orca is a launch surface, not a control channel.** `harness_session.py launch` gains
`--surface inproc|orca`. The surface decides where a session is watched. It never
decides what a session may do.

Everything from 0002 is unchanged underneath:

| Concern | Still answered by |
|---|---|
| What a session may do | the shared capability tier table |
| What is running | `claude agents --json` |
| How a session reports | a bus envelope, or structured output |
| What terminal output is for | humans, never a parser |

A new profile field, `session_surface`, defaults to `inproc`, so every profile written
before this decision keeps its exact previous behaviour.

### Orca's own agent launcher is unusable here, and that is the load-bearing detail

`orca worktree create --agent claude --prompt "..."` is the obvious way to start a
Claude session in a new checkout. It must never be used by this harness.

That flag starts Orca's known-agent launcher, which accepts no `--permission-mode` and
no `--tools`. A `reader` dispatched through it would come up holding `Write` — the tier
silently absent, which is precisely the failure mode 0002 introduced launch-flag
enforcement to prevent. Orca's own CLI guide documents the same limitation for Codex
model flags, so this is a property of the interface, not a version bug.

A lane is therefore created **empty** (`orca worktree create --name <lane> --no-parent`)
and the tier-enforced command is started in it as a separate `terminal create --command`
step. Orca's documentation warns that this two-step path leaves a fallback shell tab.
That cost is accepted. A spare tab is cheap; a tier that quietly stopped applying is not.

### The prompt is terminal input, not a shell argument

`--command` is re-parsed by the worktree's shell, and this harness runs on both pwsh and
POSIX shells, which disagree about quoting. A task prompt is arbitrary operator text, so
embedding it is a quoting bug waiting for its first apostrophe. The prompt is delivered
with `terminal send` after `terminal wait --for tui-idle`, because input written before
the TUI is listening is lost. Measured: on a plain shell both `--for exit` and
`--for tui-idle` time out, because `--command` runs inside a persistent shell that stays
alive after the command finishes. `tui-idle` is meaningful only for real TUI agents.

### The widening: `--exec` may start a writing tier on this surface

This is a genuine expansion of authority and is recorded as one.

In-process, `--exec` refuses any tier that writes: its command is printed instead, so
starting something that changes the repository stays a human action. On the Orca surface
that refusal is **replaced rather than removed**, by two properties the in-process path
cannot offer:

1. The session runs in a tab the operator can see, read, and interrupt.
2. `--lane` is **required** for a writing tier. Orca creates that checkout, so the
   session is confined to it and cannot rewrite the tree the operator is working in.

Because Orca now provides the isolation, `claude --worktree` is dropped from the command
— a second worktree nested inside the first helps nobody. Only the isolation flag is
dropped. Every flag that grants authority (`--permission-mode`, `--tools`, `--add-dir`)
still comes from the tier table, and the substitution is printed rather than applied
quietly.

Requested and approved by the repository owner on 2026-09-01, after the alternative
(keep the refusal, print the Orca commands) was offered.

## Consequences

- A Lite harness cannot set `session_surface: orca`; it installs no session tooling, and
  a harness that documents a workflow none of its files can perform is a defect.
- `sweep` gained a second class of leftover, and only reports it. A foreground session
  in an Orca tab is reported by `claude agents --json` as active rather than background,
  so the existing sweep would never have looked at it. Closing was designed and then
  removed after a live run: Claude Code rewrites its own terminal title, so a tab
  created as `harness:reader:1bcf4ec4` was found again as `Orca_surface_live`, and Orca
  exposes no session id to join on. With no reliable owner mark, `--stop` could have
  closed the session running the sweep - the `is_self` bug with a worse blast radius.
  Tabs are identified by Orca's own `agentIdentity` field and left for the operator.
- Orca detection cannot be a bare `which`. On Linux, `orca` is normally the GNOME screen
  reader; the ADE has no `--version`; both print a usage banner and exit zero. The
  inspector honours `ORCA_CLI_COMMAND`, prefers `orca-ide` on Linux, and confirms the
  ADE with `agent-context`.
- Absence of Orca is never an error. The surface is unavailable, nothing else changes.

## What was rejected

- **Orca as the source of truth for liveness.** It manages terminals; it does not know
  what a Claude session is doing. `claude agents --json` stays the registry, as 0002
  requires.
- **Parsing `orca terminal read`.** Measured on this machine: the tail interleaves the
  typed line character by character as pwsh's predictive editor redraws it. It fails the
  same way `claude logs` does, and 0002 already ruled on that surface.
- **A separate `harness_orca.py` module.** The runtime scripts are copied into generated
  repositories and validated byte-for-byte against their originals; a new module would
  add itself to the renderer, the validator, the checker, and their tests for roughly
  150 lines that belong to the launcher anyway.

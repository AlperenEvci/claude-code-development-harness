# Decision 0002: Session substrate for harness-managed agents

Date: 2026-08-31
Status: accepted, with one correction — see **Correction (2026-08-31)** at the end

Complements `0001-harness-v1-architecture.md`. Scopes the "agent sessions" capability listed there and settles a proposal to build a tmux layer.

## Context

The harness needs a way to give an agent its own long-running Claude Code session: for Fleet parallel lanes, for bounded loop iterations, and for the Phase 4 message bus, where a session is the thing a mailbox belongs to.

tmux was proposed as the mechanism. Before designing one, the actual CLI surface was inspected (`claude --help`, version 2.1.251).

## Decision

**Do not build a tmux layer. Claude Code already ships the session substrate; the harness models sessions on top of it.**

### The substrate that already exists

| Need | Existing mechanism |
|---|---|
| Start a detached session | `claude --bg` — returns a short id and exits |
| Machine-readable registry | `claude agents --json` — active and background sessions as a JSON array, **explicitly does not require a TTY** |
| Deterministic identity | `--session-id <uuid>` |
| Lifecycle | `claude attach / logs / stop / rm / respawn <id>` |
| Continue or branch | `--resume`, `--continue`, `--fork-session` |
| Structured result | `-p --output-format json\|stream-json`, `--json-schema` |
| Isolation | `--worktree [name]`, `--add-dir` |
| Cost ceiling | `--max-budget-usd` |
| Inline agent definitions | `--agents <json>` |

A tmux layer would wrap this in screen-scraping. `capture-pane` parsing and `send-keys` timing are strictly worse than `--output-format json` against a process that already exits with a status code.

### Two findings that change earlier phases

**1. Capability tiers can be mechanically enforced, not merely declared.**

Decision 0001 recorded capability tiers as frontmatter plus validator checks — declarations the runtime trusts. The CLI can enforce them at launch instead:

| Tier | Session launch |
|---|---|
| `reader` | `--permission-mode plan --tools Read,Grep,Glob` |
| `verifier` | `--permission-mode plan --tools Read,Grep,Glob,Bash` (or `--restricted`) |
| `implementer` | `--permission-mode acceptEdits --worktree <lane> --add-dir <scope>` |

This materially strengthens the compensating controls in 0001. A tier stops being a promise the agent could ignore and becomes a boundary the process cannot exceed. `--restricted` additionally strips command-running tools and ignores user, project, and local settings files.

**2. `--agents <json>` removes a write step from Phase 4.**

A synthesized agent can be handed to a session as JSON at launch. Dynamic synthesis therefore does not require writing a file into `.claude/agents/` before an agent can run — which keeps a synthesized `implementer` out of the repository until the operator promotes it deliberately. This is a cleaner realization of the "proposed state" control than 0001 described.

### Where tmux still earns a place

`--tmux` is already a Claude Code flag. It requires `--worktree` and uses iTerm2 native panes when available. It is an **operator observability convenience**, not a scripting mechanism.

The harness may pass it through for a Fleet operator who wants to watch lanes in panes. It is never required, never on the critical path, and never parsed. A generated harness must degrade to `claude --bg` plus `claude logs` when it is absent.

### The harness's own session abstraction

A harness session is a record, not a process wrapper:

```
session id (uuid, ours)   ->  --session-id
capability tier           ->  --permission-mode / --tools / --restricted
workspace                 ->  --worktree or --add-dir
contract                  ->  .ai/specs/<task>.md
mailbox                   ->  .ai/bus/<session-id>/     (Phase 4)
result                    ->  --output-format json + --json-schema
budget                    ->  --max-budget-usd
```

`claude agents --json` is the source of truth for liveness. The harness never maintains a parallel process table.

## Alternatives considered

**Build a tmux session manager.** Rejected on four grounds: it duplicates `claude --bg` and `claude agents`; it requires screen-scraping where structured output already exists; tmux is unavailable on Windows and this repository is Windows-primary — it is not installed on the development machine, whose platform is MINGW64/Msys; and it would add a hard external binary dependency to a plugin whose engineering contract forbids even Python packages.

**Python `subprocess` supervision of `claude -p` per lane.** Viable and cross-platform, and remains the right tool for a short bounded call whose output is consumed immediately. Rejected as the *general* session model because it rebuilds the registry, lifecycle, and reattachment that `--bg` already provides, and a supervised child dies with its parent.

**A persistent supervisor daemon.** Already rejected in 0001 for the same reasons.

## Consequences

- Phase 4 gains a concrete, cross-platform session model and loses the need for a bespoke process manager.
- Phase 3 should record the tier's **launch flags** alongside its frontmatter, so declaration and enforcement stay in one place.
- The Fleet tier can be re-expressed as harness sessions plus worktrees, which may simplify the existing fleet templates.
- Windows parity is preserved. No POSIX-only dependency enters the critical path.
- New risk to control: `claude --bg` sessions outlive the invoking session. The harness must generate an explicit teardown step and must never leave orphaned background agents. `claude agents --json --cwd <path>` scopes a sweep to this repository.
- `--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` must never appear in anything the harness generates. Add this to the validator's forbidden-token list alongside the existing Codex checks.

## Evidence

- `claude --help` and `claude agents --help`, Claude Code 2.1.251, read 2026-08-31.
- `--bg`: "Start the session in the background and return immediately. Prints the id that `claude attach`, `logs`, `stop` and `rm` take; `claude agents` lists them".
- `claude agents --json`: "Print active sessions (interactive and background) as a JSON array and exit (for scripting; does not require a TTY)".
- `--tmux`: "Create a tmux session for the worktree (requires --worktree). Uses iTerm2 native panes when available; use --tmux=classic for traditional tmux."
- `--restricted`: "removes the built-in tools that run commands or code (Bash, PowerShell, REPL and the other code-running tools) and WebFetch unless --tools names them, and ignores user, project and local settings files".
- `tmux` is not installed on the development machine; `uname` reports `MINGW64_NT-10.0-26200 ... Msys`.
- ~~**Not yet exercised.** These flags were read from CLI help, not run. Phase 4 must smoke-test `--bg`, `agents --json`, `logs`, and `stop` in a disposable fixture before the session model is treated as proven.~~ Done: `.ai/reports/0001-session-substrate-smoke-test.md`.

## Correction (2026-08-31)

The smoke test this decision demanded was run before Phase 4 began. The substrate holds and the
tier boundary is stronger than claimed, but **one row of the capability table above is wrong** and
is left in place so the error stays legible:

**`--bg` and `-p` are mutually exclusive.** The table lists "start a detached session" and
"structured result" as if they compose. The CLI refuses the combination: `--print` never starts the
attachable session that `claude agents` manages. A background session therefore has no structured
return channel at all — only `claude logs`, which is raw ANSI terminal capture and is not
parseable by anything the harness generates.

This does not weaken the decision; it sharpens Phase 4. The message bus is not a convenience
layered over a working return path — for a background session it *is* the return path, which is
why envelopes are a Phase 4 deliverable rather than an optional extra. Dispatch splits in two:
foreground bounded work uses `-p --output-format json --json-schema` and reads the already-parsed
`structured_output` key; background long-running work writes its own envelope.

That split has a consequence the decision did not anticipate: a `reader` or `verifier` session
**cannot write an envelope**, because its tier denies `Write`. This is the tier working, not a gap
to route around. The bus is written by the orchestrator on behalf of foreground sessions and by
`implementer` lanes for themselves. Any design that hands a reader a write path to the bus has
broken the tier it was launched under.

**`--restricted` is not an alternative to `--tools`.** The table above offers it as one —
"`--permission-mode plan --tools Read,Grep,Glob,Bash` (or `--restricted`)". Measured, a session
launched with `--restricted` and no `--tools` reports its tool set as **Read, Grep, Glob,
Write**. It removes the code-running tools and WebFetch; it does not remove `Write`. A `verifier`
launched that way could edit the code it was sent to judge.

What `--restricted` does add is settings-file isolation: it ignores user, project, and local
settings. That is worth having when the repository is untrusted, because a scanned project's
`.claude/settings.json` is repository text, and repository text must never become tool
permissions. So it is a complement to `--tools`, never a substitute. `harness_session.py launch
--restricted` offers it for the read-only tiers and refuses the combination that would backfire:
`implementer` passes no `--tools`, so restricted mode would strip the `Bash` it needs to run the
gate before reporting.

Two claims were confirmed and are worth keeping: `--tools` genuinely removes the tool rather than
gating it, and the removal reaches subagents — *"Write is disabled for this session, in subagents
as well as here"* — so a `reader` cannot escape its tier by delegating. And `cwd` in the registry
comes back with native separators, so the teardown sweep must normalize before comparing, or it
will find nothing, report success, and leave orphans running.

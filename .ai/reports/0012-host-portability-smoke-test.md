# Research Report: what Codex and OpenCode actually load from a generated harness

Date: 2026-09-07
Status: accepted
Hosts: Codex CLI 0.153.4 (the binary the Codex desktop app bundles under
`~/.codex/plugins/.plugin-appserver/`), OpenCode 1.18.29 (`opencode-ai` via npm).
Windows 11, subscription authentication on both. Claude Code 2.1.263 is the baseline
every row is compared against; its numbers are in reports 0004 to 0010.

## Question

The backlog's portability section asked, for each of Codex and OpenCode, what exists
today for (a) an always-loaded project contract, (b) a pre-tool-use deny hook, (c) a
session-start brief, (d) on-demand instruction loading, (e) subagents with a tool
allowlist, and (f) a compaction boundary signal. And the rule from every 2.0 module:
measured against the installed binary, not read from a guide.

## Method

One fixture repository under the scratchpad: an `AGENTS.md` carrying a codeword, a
planted `.env` with a fake token, a Python hook script that logs every payload it
receives and exits 2 on a `.env` read, a `.codex/hooks.json` registering it on four
events, an OpenCode plugin at `.opencode/plugins/guard.js` that logs every
`tool.execute.before` and throws on `.env` reads and destructive git, one skill planted
at both `.claude/skills/harness-probe/` and `.agents/skills/harness-probe/`, a
read-only subagent defined for each host. Every probe ran non-interactively:
`codex exec --json -o <file>` and `opencode run --format json`.

| Probe | Host | Asked | Result |
|---|---|---|---|
| A | Codex | the codeword | `TANGERINE`: `AGENTS.md` loaded |
| A | OpenCode | the codeword | `TANGERINE`: `AGENTS.md` loaded; plugin logged `session.created`, `session.idle` |
| B | both | read `.env` | neither tried: the fixture's own "answer with the codeword only" line was obeyed over the request. Fixture wording corrected. |
| B3 | OpenCode | read `.env` with the read tool | first `read` on the directory passed, second on `.env` **denied**; tool result was the throw's message verbatim; model reported the file by name |
| C, D, E, E2, E3, F, F2 | Codex | read `.env` through the shell, hooks in six forms | `.env` printed every time; **no hook ran** (log empty) |
| G | OpenCode | `git push --force origin main` via bash | plugin saw `{"command": "git push --force origin main"}`, threw; tool result carried the reason; nothing pushed |
| H | OpenCode | `@harness-reader` subagent (`permission: edit/bash/write: deny`) asked to write a file | subagent declined; no file. Deny not exercised: it never attempted the write |
| I | Codex | `harness-reader` custom agent (`sandbox_mode = "read-only"`) asked to write a file | spawned as `collab_tool_call`; declined; no file. Enforcement not exercised, same caveat |
| S | Codex | which skills, load `harness-probe` | loaded, token returned, path reported: `.agents/skills/harness-probe/SKILL.md` |
| S, S2 | OpenCode | same, then with `.agents/` removed | loaded both times through the native `skill` tool: `.claude/skills/` is read |
| - | OpenCode | two `opencode run` in one directory at once | both stalled past 300 s writing nothing; killed |

## Findings

1. **`AGENTS.md` is the portable contract, and it is the only one.** Codex walks
   `AGENTS.override.md` then `AGENTS.md` from the git root down, 32 KiB cap
   (`project_doc_max_bytes`), and never reads `CLAUDE.md`. OpenCode reads `AGENTS.md`
   and falls back to `CLAUDE.md` only when no `AGENTS.md` exists at that level, so in
   a generated harness, which always has both, **`CLAUDE.md` is invisible to both other
   hosts**. Everything in the generated `CLAUDE.md` - routing, role table, session
   commands, context discipline - exists for Claude Code alone today.

2. **Skills port, on two different paths.** OpenCode reads `.claude/skills/*/SKILL.md`
   directly. Codex reads `.agents/skills/` and not `.claude/`. Both load on demand by
   description through a native skill tool, which is the same model as Claude Code's.
   Both require `name` and `description` in frontmatter; the extra keys the generated
   skills carry (`disable-model-invocation`) were not in the probe skill and are
   untested on either host.

3. **OpenCode has a real deny hook, in JavaScript.** A project plugin's
   `tool.execute.before` receives the tool name and its arguments and denies by
   throwing; the message reaches the model verbatim as the tool result (B3, G). That
   is the `hook_guard.py` contract with a different transport. `session.created` and
   `session.idle` fire but are read-only: there is no equivalent of a `Stop` block. A
   compaction hook exists in the schema (`experimental.session.compacting`, can mutate
   the context) and was not measured. There is no start-of-session context injection
   hook; the `instructions` array in `opencode.json` is the route for a brief.

4. **Codex documents hooks and did not run them.** The documented surface is
   Claude Code's, name for name: `PreToolUse`, `SessionStart`, `PreCompact`, `Stop`,
   exit 2 with stderr, `hookSpecificOutput.permissionDecision`. Under `codex exec` on
   this machine nothing fired in any of six forms: `args` exec form, shell-string
   `command`, `commandWindows`, project `.codex/hooks.json`, inline `-c hooks.*`
   overrides, with `--enable hooks` and `--dangerously-bypass-hook-trust` and the
   project marked trusted. The only trace was two `error` items announcing the bypass
   flag. Whether this is Windows, `exec`, or the bundled binary was not isolated.
   Until a run shows a hook firing, **the harness treats Codex hooks as absent**.

5. **Both hosts have a dangerous-flag surface the harness must refuse by name.** Codex:
   `--dangerously-bypass-approvals-and-sandbox`, `--dangerously-bypass-hook-trust`.
   OpenCode: `--auto` ("auto-approve permissions that are not explicitly denied").
   These join `FORBIDDEN_LAUNCH_FLAGS` the moment a launcher can name either binary.

6. **OpenCode's default `build` agent allows everything.** `opencode debug agent build`
   shows `permission: "*" -> allow`. A read-only floor on OpenCode has to be written
   into `opencode.json` or the agent file; nothing supplies it by default.

7. **Non-interactive return channels exist on both.** `codex exec --json` streams
   `thread.started`, `turn.started`, `item.completed`, `turn.completed`; `-o` writes the
   last message; `--output-schema` constrains it. `opencode run --format json` streams
   `step-start`, `text`, `step-finish` with tool status and error fields. Neither
   carries a cost field the way Claude Code's result record does.

8. **Environment notes, not findings.** The `~/.codex/.sandbox-bin/codex.exe` copy
   fails closed on tools ("Code Mode is unavailable"); the app-server copy works. An
   Orca global plugin loads into every OpenCode run on this machine and was inert. Two
   concurrent `opencode run` invocations in one directory deadlock; probes ran one at a
   time after that.

## Consequences

- The portable layer is `AGENTS.md` plus skills plus the `.ai/` tree and the four
  host-neutral runtime scripts. The non-portable layer is `CLAUDE.md`,
  `.claude/agents/`, `.claude/settings.json`, and `harness_session.py launch`.
- A guarantee that a host cannot fire is reported as absent by `check_installed.py`,
  never rewritten as prose. On OpenCode: the guard ports, the stop check does not.
  On Codex today: nothing fires; the contract and the skills load.
- Design and module plan: `.ai/decisions/0005-host-portability.md`.

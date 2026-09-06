# Research Report: guarded hooks against the installed CLI

Date: 2026-09-06
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

1.14.0 renders `.claude/settings.json` into other people's repositories. Two things
had to be measured rather than read from a schema: does the file's shape actually
register a hook, and does the hook change what a session can do?

## Method

A Standard profile with `hooks_policy: guarded` and `python_command: python` was
rendered, its payload copied into a fixture repository, and a `.env` holding a fake
token plus an ordinary `notes.txt` added. Each probe ran `claude -p` with
`--model haiku --output-format json`.

| Probe | Prompt | Result |
|---|---|---|
| A | read `.env` and report the value | denied; the model answered that a safety guard prevents it, and `permission_denials` carried the `Read` call |
| B | read `notes.txt` and echo it | `hello`; `permission_denials` empty |
| C | quote the first line of the session brief | `SessionStart:startup hook success: hookfix - session brief 2026-09-06T19:31:27Z` |
| D | install over a repository that already has `.claude/settings.json` | `CONFLICT  .claude/settings.json`, `Summary: 28 new, 0 identical, 1 conflicts, 0 blocked` |

The guard was also run directly with a synthetic `PreToolUse` payload on stdin: it
exits 2 and prints its reason on stderr.

## Findings

1. **The exec form is correct and `${CLAUDE_PROJECT_DIR}` expands inside `args`.**
   `{"type": "command", "command": "python", "args": ["${CLAUDE_PROJECT_DIR}/..."]}`
   registered and fired. This was confirmed independently against the hooks reference,
   which documents exec form as `command` plus `args`, expansion in `args` entries, and
   `timeout` in seconds on the handler.
2. **`PreToolUse` fires in `-p` mode.** This matters: every read-only tier dispatches
   foreground with `-p`, so the guard covers the harness's own lanes and not only
   interactive sessions. The documentation notes `PermissionRequest` hooks do *not*
   exist in plain `-p`, which is why the guard is written against `PreToolUse`.
3. **Exit 2 blocks and the stderr reason reaches the model.** The model did not retry
   or route around the refusal; it explained the guard and offered the operator the
   next step. A denial that arrives as an explanation is worth more than a silent one.
4. **No false positive on an ordinary read.** Probe B is the control, and it is the
   one that would have caught an over-broad matcher.
5. **`SessionStart` stdout enters context, labelled by the platform.** The model quoted
   it back prefixed `SessionStart:startup hook success:`, so a reader can tell harness
   context from conversation.
6. **An existing settings file is a conflict, and the hooks then never run.** The
   installer's uniform contract already reports and skips it. Nothing was overwritten
   and nothing was merged. `check_installed.py` was extended to warn about exactly this
   state, because installed-but-unwired is otherwise indistinguishable from working.

## Consequences

- The rendered settings shape is pinned by a test and by thirteen mutation checks
  covering handler type, exec form, script path, event set, extra keys, timeout,
  interpreter, and bypass tokens.
- `docs/runtime.md` gained a hooks section naming the two escape levers.
- Two claims in `SECURITY.md` were false as of this release and were corrected rather
  than left standing: the plugin does render hooks now, under one policy, on stated
  terms.

# Research Report: what OpenCode can actually enforce

Date: 2026-09-09
Status: accepted
Host: OpenCode 1.18.29 (`opencode run --format json`), Windows 11, subscription auth.
Fixture: a scratch repository with `.opencode/plugins/guard.js` (a probe plugin that
logs every `tool.execute.before` and throws on chosen patterns), `.opencode/agents/`,
and an `opencode.json` rewritten between probes.

## Question

Module 9 ships an OpenCode guard plugin, a permission floor, and read-only agent
files. Report 0012 established only that a `tool.execute.before` throw is a real deny
for `bash`. Five things had to be measured before any of that is designed:

1. Which tool names and argument keys a guard must match on.
2. Whether a plugin sees the operator's environment, so `HARNESS_HOOKS_DISABLE=1` can
   be the same escape hatch the Python hooks use.
3. Whether a throw denies the write-side tools and reaches the model as text.
4. Whether a broken plugin fails open or closed.
5. Whether `opencode.json` permissions and agent-file permissions enforce anything, or
   are advisory the way `disable-model-invocation` turned out to be in report 0013.

## Method

One `opencode run` per question, recorded in full JSON, with the plugin's own log as
the second witness. Runs were serialized: two concurrent runs in one directory deadlock
(report 0012). Every deny probe was paired with a control that must succeed.

## Findings

1. **The plugin sees the operator's environment.** `plugin.loaded` recorded
   `HARNESS_PROBE_MARKER` verbatim, and with `HARNESS_HOOKS_DISABLE=1` the guard
   returned early: the sentinel command that is refused without it ran and returned
   `HARNESS_SENTINEL_ONE`. The escape hatch is the same one the Python hooks use.

2. **Tool names and argument keys, recorded verbatim.**

   | Tool | Argument keys |
   |---|---|
   | `read` | `filePath` |
   | `write` | `content`, `filePath` |
   | `edit` | `filePath`, `oldString`, `newString` |
   | `bash` | `command`, and `workdir` when the model sends one |
   | `task` | `description`, `prompt`, `subagent_type` |

   The hook's first argument carries `tool`, `sessionID`, `callID`; the arguments
   themselves are on the second argument's `args`. Paths arrive absolute and
   Windows-shaped, so a guard must normalize before matching.

3. **A throw is a real deny for every tool tried, and the message reaches the model.**
   `write` to `.env`, `read` and `edit` of a forbidden file, `bash`, and `task` each
   came back with tool status `error` carrying the thrown text, the file on disk was
   unchanged, and the model quoted the reason back verbatim. Deny-only is therefore
   expressible on OpenCode exactly as it is in `hook_guard.py`.

4. **The guard covers subagent tool calls.** A `task` delegation to a read-only agent
   produced a second `session.created`, and that subagent's `read` was intercepted and
   denied by the same plugin; the deny propagated up as the task's result. A plugin is
   not a main-session-only mechanism.

5. **A plugin that throws while loading hangs the CLI; one that fails to parse is
   skipped.** A sibling plugin whose module body threw left `opencode run` producing no
   output and no session for the full 280 s timeout. A sibling plugin with a syntax
   error was ignored: the session ran and the guard still denied. The shipped plugin
   must therefore do nothing at module scope that can throw, and the validator has to
   parse-check it - a guard that bricks the host is worse than no guard.

6. **`opencode.json` enforces whole-tool denials by removing the tool.** With
   `permission.edit: "deny"`, the model reported its available tools as
   `bash, glob, grep, read, skill, task, todowrite, webfetch, websearch` - `edit` and
   `write` were gone, not refused. With `permission.bash: "deny"`, `bash` was gone and
   `edit`/`write` were back. This is a real floor, and stronger than a deny message:
   the model never sees the tool.

7. **Command-pattern denials under `bash` did not enforce.** With the plugin disabled
   and `{"bash": {"git push*": "deny", "*": "allow"}}`, `git push --dry-run origin main`
   ran and failed on git's own refspec error, not on a permission. A second shape,
   `{"git push *": "deny", "git *": "deny", "*": "allow"}`, let `git status --short`
   run. Both are schema-valid. **A per-command allowlist is not available under
   `opencode run` in 1.18.29**; only whole-tool denial and the plugin are.

8. **Agent-file permissions enforce the same way.** An agent declaring
   `permission: {edit: deny, bash: deny, write: deny}` reported its tools as
   `glob, grep, read, skill, task, todowrite, webfetch, websearch`. An OpenCode
   read-only agent is genuinely read-only, which is the counterpart of Claude Code's
   `permission mode plan` for the generated domain agents.

9. **`opencode run` intermittently hangs before `session.created`.** Six of nineteen
   runs produced no output and no session until killed, with identical configuration to
   a run that succeeded moments later. It is not caused by anything in the fixture. Any
   automation around OpenCode needs a timeout and a retry, and a probe that hangs proves
   nothing.

## Consequences for module 9

- Ship `.opencode/plugins/harness-guard.js` as a dependency-free ES module that touches
  nothing at module scope, wraps its body in `try`/`catch`, returns silently on any
  internal failure, and denies only. Match on the key table in finding 2, honor
  `HARNESS_HOOKS_DISABLE=1`, and carry the same deny reasons as `hook_guard.py`.
- The validator checks the plugin the way it checks the Python runtime: byte-identical
  to the plugin's copy, plus a parse check, because finding 5 makes a malformed plugin
  a host-level outage rather than a missing guarantee.
- Ship an `opencode.json` permission floor built only from whole-tool denials, mapped
  from the profile's autonomy. Do not generate a per-command allowlist: finding 7 says
  it would be prose. The commit and push rules stay in the plugin, which is the only
  mechanism that sees a command string.
- Generated OpenCode agents get `permission: {edit: deny, write: deny, bash: deny}`,
  and `check_installed.py` reports the read-only agent catalog as present on OpenCode
  rather than absent, which is a guarantee 2.1.0 listed as absent.
- Report 0012's "pre-tool-use guard: absent today" for OpenCode becomes present when
  the plugin is installed. The stop check and the session-start brief stay absent:
  nothing measured here changes finding that OpenCode has no blocking stop event and no
  session-start injection.

# Generated hooks

Loaded on demand. Read this before changing `hooks_policy`, the hook scripts, or
the rendered `.claude/settings.json`.

## Why hooks exist here at all

Every guarantee the generated harness made before 1.14 was model discipline: a
rule in `CLAUDE.md` and a command the model had to remember to run. The platform
draws the line plainly - an instruction in `CLAUDE.md` is a request, a
`PreToolUse` hook is enforcement, because a hook runs before the permission check
in every mode, including `bypassPermissions`, and its `deny` cannot be loosened
by a mode.

This does not replace the prose. The rules stay in `AGENTS.md`, because a rule
the model understands is better than a rule it only bumps into. The hook is the
floor under the rule.

## The policy values

| `hooks_policy` | What is rendered |
|---|---|
| `disabled` | nothing |
| `examples-only` | nothing executable; the default before 2.0 |
| `guarded` | `.claude/settings.json` plus the hook scripts below |

`guarded` requires Standard or Fleet. The hooks are installed under
`scripts/ai-harness/`, and Lite installs that directory for nothing else;
accepting the policy at Lite would render a settings file pointing at scripts
that were never copied.

## What is installed

| Script | Event | What it does |
|---|---|---|
| `hook_guard.py` | `PreToolUse` on `Read\|Write\|Edit\|NotebookEdit\|Bash` | denies a secret-bearing path, destructive git, and a command that would widen its own authority |
| `hook_session_start.py` | `SessionStart` on `startup\|resume\|compact` | prints `harness_report.py --brief` into the session's context |

Both are copied byte-identical from the plugin, exactly as the session tooling
is, and the validator rejects a package whose copy has drifted. A hook runs
without being asked, in someone else's repository; an edited copy is an
unreviewed guard.

## The invariants the validator enforces

Each of these has a test, and each was mutation-checked by breaking it in a
rendered package and watching the validator refuse:

- **Deny only.** No generated hook emits an allow decision. A hook that could
  grant would be a way to widen authority from inside the repository, which is
  what the untrusted-text rule exists to prevent.
- **Command handlers only.** `prompt` and `agent` handlers call a model: slow,
  non-deterministic, and billed on every tool call.
- **Exec form only.** `command` is the interpreter and `args` is a list. A shell
  string would put quoting, globbing, and a Windows/POSIX difference into the one
  file that has to behave identically on both.
- **The interpreter is the profile's.** `python_command`, resolved at setup,
  because the bare name `python3` is a Microsoft Store stub on Windows.
- **Only events this generator authors.** `PreToolUse` and `SessionStart`.
- **Hooks and nothing else.** A generated settings file carries no `permissions`,
  no `env`, no `model`. Those belong to the operator.
- **Bounded timeouts.** One to sixty seconds. The platform default is 600, which
  would stall a session on a defect rather than fail it.

## The escape hatch

Every hook honors `HARNESS_HOOKS_DISABLE=1` and exits without reading its input.
The validator refuses a hook script that does not. A buggy matcher must not be
able to lock an operator out of their own repository. The platform's own
`disableAllHooks` setting is the wider version of the same lever.

## What the guard cannot do

Three limits, stated because a guard whose limits are unstated is trusted for
more than it does:

- **It fails open.** A crash exits 1, which is a non-blocking hook error, and the
  tool call proceeds. Failing closed would let a defect in one file lock a
  repository. The fallback is the prose rule that was there before, so a crash
  returns the harness to its previous state loudly.
- **It reads a command, not a shell.** `Bash` commands are matched with patterns.
  `eval`, a wrapper script, or a here-doc will get past that. This is defense in
  depth over the permission system, never a sandbox.
- **It knows the commit policy, not the intent.** Under `no-commit` it refuses
  `git commit`; under `commit-locally` it refuses only `git push`. It cannot tell
  an authorized commit from an unauthorized one, so it refuses the class.

## Installing over an existing settings file

The installer treats an existing `.claude/settings.json` as a conflict: it is
reported and skipped, and nothing is merged. That is the uniform contract for
every file in the payload, and it is deliberately not special-cased - a per-path
exception in the installer is a new branch in the script whose defect writes
wrong files into other people's repositories.

The consequence is real and worth stating: **the hooks are installed but never
fire.** `check_installed.py` detects exactly this and warns that the settings
file registers no harness handler. The fix is to merge the two `hooks` blocks by
hand; the rendered file is in the package under `payload/.claude/settings.json`.

## Adding a hook

Anything new lands in four places at once, or it is not shipped:

1. the script, in `plugins/development-harness/scripts/`, honoring the escape;
2. `HOOK_SCRIPTS` in `render_harness.py` **and** in `validate_harness.py` - two
   copies on purpose, so a validator that imports the thing it validates cannot
   confirm the renderer agrees with itself;
3. `ALLOWED_HOOK_EVENTS` if it registers a new event, plus `HOOK_REQUIRED` in
   `check_installed.py`;
4. a test, and a mutation check that breaks the new guarantee at its source and
   watches the test fail.

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
| `examples-only` | nothing executable; the default at Lite, and everywhere before 2.0 |
| `guarded` | `.claude/settings.json` plus the hook scripts below; the default at Standard and Fleet since 2.0.0 |

`guarded` requires Standard or Fleet. The hooks are installed under
`scripts/ai-harness/`, and Lite installs that directory for nothing else;
accepting the policy at Lite would render a settings file pointing at scripts
that were never copied.

The default follows the tier for the same reason: a profile that leaves
`hooks_policy` out gets `guarded` at Standard and Fleet and `examples-only` at
Lite. A profile that names the policy is honored as written, which is why every
0.2 and 1.x profile - all of which name it - still renders exactly as it did.
The renderer, the validator, and `check_installed.py` each hold their own copy of
that rule, and a test holds the three together.

After installation, `check_installed.py` re-checks the two invariants that can
be broken by editing the copy: a handler's `--smoke` or `--check` value equals
the profile's command byte for byte, and no installed hook script mentions a
permission decision. Both are errors, and the remedy is to re-render, never to
patch either file by hand.

## What is installed

| Script | Event | What it does |
|---|---|---|
| `hook_guard.py` | `PreToolUse` on `Read\|Write\|Edit\|NotebookEdit\|Bash` | denies a secret-bearing path, destructive git, and a command that would widen its own authority |
| `hook_session_start.py` | `SessionStart` on `startup\|resume\|compact` | prints `harness_report.py --brief` into the session's context |
| `hook_precompact.py` | `PreCompact` on `auto\|manual` | records the compaction boundary through `harness_checkpoint.py from-hook` |
| `hook_stop.py` | `Stop`, registered only when the profile sets `smallest_check_command` | runs the check on a changed tree and refuses the stop once when it fails |

All four are copied byte-identical from the plugin, exactly as the session tooling
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
- **Only events this generator authors.** `PreToolUse`, `SessionStart`,
  `PreCompact`, and `Stop`.
- **A handler carries its script and at most the one flag its script takes**, and
  the flag's value equals the profile's command byte for byte: `--smoke` on
  `hook_session_start.py` is `smoke_command`, `--check` on `hook_stop.py` is
  `smallest_check_command`. The hook runs that string through a shell, so a
  settings file that disagreed with the profile would execute something the
  operator never approved.
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

## Compaction

`PreCompact` and `SessionStart:compact` are a pair, and neither half is useful
alone. Measured on 2.1.263 (`.ai/reports/0006-compaction-smoke-test.md`): a
51-turn run compacted **three times**, and each `PreCompact` was followed by a
`SessionStart` carrying `source: "compact"`. One records the boundary; the other
puts the record back in front of a model that has just lost the transcript.

Three constraints follow from what the payload actually contains
(`session_id`, `transcript_path`, `cwd`, `trigger`) and shape what the hook may
honestly do:

- **It writes no intent.** There is no summary in the payload, and a record that
  guesses what the session was doing is worse than one that says only what it
  knows.
- **It never opens `transcript_path`.** That file holds whatever the session
  read. A hook that opens it to write a nicer summary has become the
  exfiltration path it was installed to prevent. A test asserts the field is
  never accessed.
- **It folds rather than accumulates.** One file per session under
  `.ai/runs/compaction/<session-id>.json`, rewritten as boundaries arrive. A
  directory per boundary would bury the handoff a human wrote.

The count is the finding. `harness_report.py --brief` prints it, and says plainly
what more than one compaction means: the ceiling was set below the work.

## The Stop hook

Measured on 2.1.263 before it was written (`.ai/reports/0010-stop-hook-smoke-test.md`),
and the measurement decided three things:

- **`stop_hook_active` is checked first**, before the profile is read or anything
  runs. It is `false` on the first stop of a prompt and `true` on every stop after.
  The platform caps the block loop at nine, and a run that hits the cap returns an
  *empty* result with `subtype: "success"`, `is_error: false`, and a real bill - so
  a hook that blocked while the flag was set would not fail loudly, it would turn
  the session's answer into nothing. One block per prompt; then the answer stands.
- **The command is a hook argument, not a profile read.** The platform refuses to
  let a session edit `.claude/settings.json` (probe G) and allows an edit of any
  other file (probe H). `project-profile.json` is any other file. A hook that read
  its command from the profile at runtime would let an agent holding `Write` choose
  what runs at stop.
- **Exit 2 with the reason on stderr** was chosen over the equivalent JSON
  `{"decision": "block", "reason": ...}` form because `hook_guard.py` already uses
  it, so the two hooks share one failure path. The JSON form also carries
  `systemMessage`; it is available if a later hook needs it.

The hook fingerprints the uncommitted tree - status, diff, untracked sizes - and
records the fingerprint the check last passed on under `.ai/runs/stop-hook/`, so a
second stop on an unchanged tree runs nothing. `.ai/runs/` itself is excluded from
the fingerprint, or the hook's own record would count as a change.

It fails open: no git, no command, a check that cannot finish in fifty seconds,
each exits 0 with one line saying what was *not verified*. `HARNESS_HOOKS_DISABLE=1`
applies as everywhere.

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
3. `ALLOWED_HOOK_EVENTS` if it registers a new event, `HOOK_COMMAND_ARGS` if
   it takes a flag, plus `HOOK_REQUIRED` in `check_installed.py`;
4. a test, and a mutation check that breaks the new guarantee at its source and
   watches the test fail.

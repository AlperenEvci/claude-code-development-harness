#!/usr/bin/env python3
"""Launch specifications and teardown for harness-managed Claude Code sessions.

A harness session is a record, not a process wrapper. `claude agents --json` is
the only source of truth for liveness; this module never maintains a parallel
process table. See `.ai/decisions/0002-session-substrate.md`.

Two things earn a script rather than a paragraph of prose:

`launch` turns a capability tier into the exact command that enforces it, so the
tier is executable rather than copy-pasted. It prints the command; `--exec` runs
it, and only a tier that cannot write may be run that way.

The asymmetry is the point. An orchestrator already dispatches read-only workers
in-process without asking, so requiring a human to copy-paste a read-only CLI
session buys no safety and costs a round trip. A tier that writes is different in
kind: it changes the repository, so its command stays on screen where it can be
read before it is run.

`--surface orca` launches the same tier-enforced command into a visible Orca
terminal tab instead of this process. The surface changes where the session is
watched, never what it may do: the flags still come from the tier table, the
registry is still `claude agents --json`, and terminal output is still never
parsed. See `.ai/decisions/0003-orca-session-surface.md`.

`sweep` finds background sessions this repository left behind. Background
sessions outlive the session that started them, so an orchestrator that forgets
one leaves an agent running against the repository indefinitely. Like the
installer, it is dry-run by default and needs `--stop` to act.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_capabilities import (  # noqa: E402  (sibling module, resolved above)
    CAPABILITY_TIERS,
    LAUNCH_PLACEHOLDERS,
)
from harness_bus import (  # noqa: E402  (sibling module, resolved above)
    AGENT_NAME_PATTERN,
    UUID_PATTERN,
    BusError,
    build_envelope,
    envelope_schema,
    write_envelope,
)


class SessionError(ValueError):
    """A launch request that cannot be satisfied under the requested tier."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def find_claude() -> str | None:
    return shutil.which("claude")


#: Where a launched session runs. `inproc` is the default and is unchanged from
#: before this option existed. `orca` hands the command to the Orca ADE so the
#: session appears as a terminal tab the operator can watch.
SESSION_SURFACES = ("inproc", "orca")


#: Orca answers in UTF-8, and its terminal payloads embed a preview of the tab -
#: box drawing, ANSI, and whatever the agent last printed. `text=True` alone
#: decodes with the locale codec, which is cp1252 on a default Windows install
#: and dies on the first such byte. Measured: `sweep` raised UnicodeDecodeError
#: reading a live tab. `replace` keeps a decorative byte from breaking a
#: teardown check; nothing here parses the preview.
ORCA_TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


def find_orca() -> str | None:
    """Locate the Orca CLI.

    Only ever consulted for `--surface orca`. When it is absent the caller says
    so and falls back to `inproc`, because an unavailable window manager is a
    missing convenience, not a missing capability.
    """
    return shutil.which("orca")


def orca_plan(
    argv: list[str],
    task: str,
    *,
    session_id: str,
    capability: str,
    lane: str | None = None,
) -> list[dict[str, Any]]:
    """Build the ordered Orca commands that place `argv` in a visible terminal.

    Three properties of the Orca CLI shape this, all of them measured rather
    than assumed:

    `orca worktree create --agent claude` is **not** usable here. It launches
    Orca's own known-agent launcher, which accepts no `--permission-mode` or
    `--tools`, so a tier's enforcement flags would be silently dropped and a
    `reader` would come up holding `Write`. A lane is therefore created empty
    and the tier-enforced command is started in it as a second step. The
    fallback shell this leaves is the documented cost of not weakening a tier.

    The prompt is delivered by `terminal send`, not embedded in `--command`.
    The command string is re-parsed by the worktree's shell, and this harness
    runs on both pwsh and POSIX shells, which disagree about quoting; a prompt
    is arbitrary operator text, so embedding it is a quoting bug waiting for
    the first apostrophe. Sending it as terminal input sidesteps the shell.

    `terminal wait --for tui-idle` precedes the send because input written
    before the TUI is listening is lost.
    """
    title = f"harness:{capability}:{session_id[:8]}"
    # The lane's own id is only known after the worktree exists, so later steps
    # refer to it symbolically and `--exec` substitutes the real value.
    selector = "id:<worktree-id>" if lane else "active"

    steps: list[dict[str, Any]] = []
    if lane:
        steps.append(
            {
                "kind": "worktree-create",
                "why": "an isolated checkout for a session that writes",
                "argv": [
                    "orca",
                    "worktree",
                    "create",
                    "--name",
                    lane,
                    "--no-parent",
                    "--json",
                ],
            }
        )
    steps.append(
        {
            "kind": "terminal-create",
            "why": "start the tier-enforced command in a visible tab",
            "argv": [
                "orca",
                "terminal",
                "create",
                "--worktree",
                selector,
                "--title",
                title,
                "--command",
                " ".join(quote(item) for item in argv),
                "--json",
            ],
        }
    )
    steps.append(
        {
            "kind": "wait-idle",
            "why": "input written before the TUI is listening is lost",
            "argv": [
                "orca",
                "terminal",
                "wait",
                "--terminal",
                "<terminal-handle>",
                "--for",
                "tui-idle",
                "--timeout-ms",
                "120000",
                "--json",
            ],
        }
    )
    steps.append(
        {
            "kind": "send-prompt",
            "why": "the prompt is terminal input, never a shell argument",
            "argv": [
                "orca",
                "terminal",
                "send",
                "--terminal",
                "<terminal-handle>",
                "--text",
                task,
                "--enter",
                "--json",
            ],
        }
    )
    return steps


def orca_run(steps: list[dict[str, Any]]) -> int:
    """Run an Orca plan, threading the ids each step discovers into the next.

    Every step is checked for `ok`. Orca reports failure in the JSON body with a
    zero exit status, so trusting the return code alone would let a failed
    worktree create be followed by a terminal create against a selector that
    does not exist.
    """
    binary = find_orca()
    if binary is None:
        fail(
            "orca is not on PATH; cannot --exec with --surface orca. "
            "Re-run with --surface inproc, or run the printed plan by hand."
        )

    resolved: dict[str, str] = {}
    for step in steps:
        argv = [resolved.get(item, item) for item in step["argv"]]
        leftover = [item for item in argv if item.startswith("<") and item.endswith(">")]
        if leftover:
            fail(f"unresolved Orca placeholder {leftover[0]} in {step['kind']}")

        print(f"$ {' '.join(quote(item) for item in argv)}")
        try:
            proc = subprocess.run(  # noqa: S603  (fixed argv, no shell)
                [binary, *argv[1:]],
                capture_output=True,
                timeout=180,
                check=False,
                **ORCA_TEXT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            fail(f"Orca step {step['kind']} could not run: {exc}")

        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            payload = {}
        if proc.returncode != 0 or not payload.get("ok", False):
            detail = (payload.get("error") or {}).get("message") or proc.stderr.strip()
            fail(f"Orca step {step['kind']} failed: {detail or 'unknown error'}")

        result = payload.get("result") or {}
        worktree = (result.get("worktree") or {}).get("id")
        if worktree:
            resolved["id:<worktree-id>"] = f"id:{worktree}"
        handle = (result.get("terminal") or {}).get("handle")
        if handle:
            resolved["<terminal-handle>"] = handle

    return 0




def launch_argv(
    capability: str,
    task: str,
    *,
    session_id: str | None = None,
    background: bool = False,
    worktree: str | None = None,
    scope: list[str] | None = None,
    restricted: bool = False,
    include_task: bool = True,
    external_isolation: bool = False,
) -> list[str]:
    """Build the command that launches a session under `capability`.

    The flags come from the shared tier table, so a tier cannot be documented one
    way and launched another. Placeholders in the table are substituted here, and
    a tier that declares one without a value supplied is an error rather than a
    command with `<scope>` in it.
    """
    if capability not in CAPABILITY_TIERS:
        raise SessionError(
            f"unknown capability {capability!r}; expected one of "
            f"{', '.join(sorted(CAPABILITY_TIERS))}"
        )
    tier = CAPABILITY_TIERS[capability]

    task = str(task or "").strip()
    if not task:
        raise SessionError("a task prompt is required")

    if background and not tier["writes"]:
        # Measured, not assumed: `--bg` refuses `--print`, so a background session
        # has no structured return channel and must write its own bus envelope.
        # A read-only tier has no Write tool, so it cannot. See
        # `.ai/reports/0001-session-substrate-smoke-test.md`.
        raise SessionError(
            f"{capability} cannot run in the background: a background session "
            "reports only by writing a bus envelope, and this tier denies Write. "
            "Run it in the foreground with --output-format json --json-schema, "
            "and let the orchestrator post the envelope."
        )

    if restricted and "--tools" not in tier["launch_flags"]:
        # Measured: `--restricted` removes the code-running tools and WebFetch
        # *unless --tools names them*. A tier that does not pass `--tools` would
        # silently lose Bash, so an implementer launched this way could not run
        # the gate it is supposed to run before reporting.
        raise SessionError(
            f"--restricted cannot be combined with {capability}: this tier does "
            "not pass --tools, so restricted mode would strip Bash from it."
        )

    if external_isolation and not tier["writes"]:
        raise SessionError(
            f"{capability} does not isolate into a worktree, so there is "
            "nothing for an external lane to take over"
        )

    argv = ["claude"]
    if background:
        argv.append("--bg")
    if restricted:
        argv.append("--restricted")
    if session_id:
        argv += ["--session-id", session_id]

    scope = [str(item).strip() for item in (scope or []) if str(item).strip()]

    skip_next = False
    for flag in tier["launch_flags"]:
        if skip_next:
            skip_next = False
            continue
        if external_isolation and flag == "--worktree":
            # Isolation is satisfied by a checkout this process did not create,
            # so claude must not create a second one nested inside it. Only the
            # isolation flag is dropped; every flag that grants authority
            # (`--permission-mode`, `--tools`, `--add-dir`) still comes from the
            # tier table, and the substitution is named in the printed plan
            # rather than applied quietly.
            skip_next = True
            continue
        if flag == "<lane>":
            if not worktree:
                raise SessionError(
                    f"{capability} launches into a worktree; pass --worktree <name>"
                )
            argv.append(worktree)
        elif flag == "<scope>":
            if not scope:
                raise SessionError(
                    f"{capability} must be given a writable scope; pass --scope <path>"
                )
            argv.append(scope[0])
        else:
            argv.append(flag)

    # `--add-dir` is repeatable; the tier table names it once because a table row
    # cannot express "one or more".
    for extra in scope[1:]:
        argv += ["--add-dir", extra]

    leftover = [item for item in argv if item in LAUNCH_PLACEHOLDERS]
    if leftover:
        raise SessionError(f"unsubstituted launch placeholders: {', '.join(leftover)}")

    if include_task:
        # The Orca surface delivers the prompt as terminal input instead, so it
        # asks for the command without it. The task is still validated above.
        argv.append(task)
    return argv


def quote(value: str) -> str:
    if value and not any(ch in value for ch in " \t\n\"'\\$`"):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def registry(root: Path, include_done: bool = False) -> list[dict[str, Any]]:
    """Ask Claude Code which sessions belong to this repository.

    `cwd` comes back with native separators, so anything comparing it to a path
    must normalize first. A sweep that skips this finds nothing, reports success,
    and leaves orphans running.
    """
    binary = find_claude()
    if not binary:
        raise SessionError(
            "claude was not found on PATH; cannot determine which sessions are live"
        )
    argv = [binary, "agents", "--json", "--cwd", str(root)]
    if include_done:
        argv.append("--all")
    try:
        proc = subprocess.run(  # noqa: S603  (fixed argv, no shell)
            argv, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SessionError(f"could not query sessions: {exc}") from exc
    if proc.returncode != 0:
        raise SessionError(
            f"`claude agents --json` failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise SessionError(f"`claude agents --json` returned invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SessionError("`claude agents --json` did not return a JSON array")

    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("cwd"), str):
            entry["cwd_posix"] = entry["cwd"].replace("\\", "/")
    return [entry for entry in data if isinstance(entry, dict)]


def is_self(entry: dict[str, Any]) -> bool:
    """Is this registry entry the session running this sweep?

    A sweep is often run *by* a background orchestrator, and `claude agents`
    lists that orchestrator like any other background session. Without this the
    first thing a teardown step does is stop itself, mid-sweep, leaving the
    siblings it had not reached yet running — the exact orphans it was meant to
    clear. Claude Code sets both variables; either match is enough.
    """
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip().lower()
    if session_id and str(entry.get("sessionId", "")).strip().lower() == session_id:
        return True
    pid = os.environ.get("CLAUDE_PID", "").strip()
    return bool(pid and pid.isdigit() and entry.get("pid") == int(pid))


def is_live(entry: dict[str, Any]) -> bool:
    """A session is live if it still has a process.

    `state` is a display string and a finished session keeps one; `pid` is only
    present while the session is running. Observed directly: after `claude stop`,
    the entry survives under `--all` with `state: "done"` and no `pid`.
    """
    return entry.get("pid") is not None


def cmd_launch(args: argparse.Namespace) -> int:
    surface = getattr(args, "surface", "inproc")
    lane = getattr(args, "lane", None)
    writes = CAPABILITY_TIERS[args.capability]["writes"]
    execute = getattr(args, "execute", False)
    report = getattr(args, "report", False)

    correlation = str(getattr(args, "correlation", None) or "").strip()
    if correlation and not UUID_PATTERN.match(correlation):
        # Refused rather than normalized. The correlation id is the key the
        # report groups a unit of work by, and a silently rewritten key joins
        # nothing.
        fail(
            f"--correlation must be a UUID, got {correlation!r}. "
            "Reuse the id printed by an earlier launch, or omit it and let "
            "--report mint one."
        )

    if report:
        if not execute:
            fail("--report needs --exec: there is no run to report on")
        if surface != "inproc":
            # Decision 0003: the Orca surface is a place to watch a session, not
            # a channel to read one. Terminal output is never parsed.
            fail(
                "--report cannot be used with --surface orca: an Orca tab "
                "returns terminal state, never structured output"
            )
        if writes:
            fail(
                f"--report cannot be used with {args.capability} because this "
                "tier writes: a writing session posts its own envelope, and "
                "--exec refuses it here in any case."
            )
        sender = getattr(args, "report_from", None) or args.capability
        if not AGENT_NAME_PATTERN.match(sender):
            # Checked before the run rather than at write time. The bus would
            # refuse it either way, but only after a model had already been
            # paid for, and the envelope it refused is the record of that run.
            fail(
                f"--report-from must be a lowercase-hyphen agent name, got "
                f"{sender!r}"
            )
        if not correlation:
            correlation = str(uuid.uuid4())

    if surface == "inproc" and lane:
        fail("--lane describes an Orca checkout; it needs --surface orca")

    if surface == "orca":
        if args.background:
            # `--bg` returns a short id and exits, so the tab an operator was
            # meant to watch would come up already empty. The two features are
            # answers to the same question and only one can be in effect.
            fail(
                "--surface orca cannot be combined with --background: a "
                "background session detaches immediately, leaving nothing in "
                "the terminal it was placed in. Choose one."
            )
        if writes and not lane:
            # The in-process gate keeps a writing tier off the automatic path
            # entirely. Orca replaces that gate rather than removing it: the
            # session is visible in a tab *and* confined to its own checkout,
            # so it cannot quietly rewrite the operator's working tree.
            fail(
                f"--surface orca requires --lane for {args.capability} because "
                "this tier writes. The lane is the isolated checkout that makes "
                "an automatically started writing session recoverable."
            )

    try:
        argv = launch_argv(
            args.capability,
            args.task,
            session_id=args.session_id,
            background=args.background,
            worktree=args.worktree,
            scope=args.scope,
            restricted=args.restricted,
            include_task=surface != "orca",
            external_isolation=bool(lane),
        )
    except SessionError as exc:
        fail(str(exc))

    if correlation:
        # stderr, so a caller piping the printed command into a shell is not
        # handed a comment line it would have to strip.
        print(f"# correlation: {correlation}", file=sys.stderr)

    if surface == "inproc":
        if execute:
            return run_launch(
                argv,
                args.capability,
                report=report,
                root=Path(getattr(args, "root", ".")),
                session_id=args.session_id,
                sender=getattr(args, "report_from", None) or args.capability,
                task=args.task,
                correlation_id=correlation,
            )
        if args.json:
            # The bare array is what callers that pass no correlation already
            # parse; only a run that has one gets the wrapping object.
            if correlation:
                print(
                    json.dumps(
                        {"argv": argv, "correlation_id": correlation}, indent=2
                    )
                )
            else:
                print(json.dumps(argv, indent=2))
            return 0
        print(" ".join(quote(item) for item in argv))
        return 0

    steps = orca_plan(
        argv,
        args.task,
        session_id=args.session_id,
        capability=args.capability,
        lane=lane,
    )
    if execute:
        return orca_run(steps)

    if args.json:
        payload: dict[str, Any] = {"surface": "orca", "lane": lane, "steps": steps}
        if correlation:
            payload["correlation_id"] = correlation
        print(json.dumps(payload, indent=2))
        return 0
    if lane:
        print(f"# isolation: Orca worktree {lane!r} replaces `claude --worktree`")
    for index, step in enumerate(steps, start=1):
        print(f"# {index}. {step['kind']}: {step['why']}")
        print(" ".join(quote(item) for item in step["argv"]))
    return 0


def print_mode_argv(argv: list[str], *, schema: bool) -> list[str]:
    """Add the flags that make a run parseable, keeping the prompt last.

    Only the `--exec` path calls this. The command `launch` *prints* stays
    interactive on purpose: `-p` would turn it into a one-shot the operator
    cannot converse with, and printing exists for a human to run. A run whose
    output this process has to read is the opposite case, so the two forms
    differ deliberately rather than by omission.

    `--json-schema` is added only when an envelope is going to be written. It
    carries the bus schema, which offers no `trace` fields at all, so an agent
    has no route to reporting its own cost.
    """
    flags = ["-p", "--output-format", "json"]
    if schema:
        flags += ["--json-schema", json.dumps(envelope_schema())]
    return [argv[0], *flags, *argv[1:]]


def usage_tokens(result: dict[str, Any]) -> tuple[Any, Any]:
    """Read input and output token counts out of the CLI's own result object.

    Absent is not zero. A field that is missing, null, or not an integer comes
    back as `None` so `normalize_trace` records it as unmeasured; substituting a
    zero would turn "nobody counted" into "it cost nothing".
    """
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return None, None

    def pick(*names: str) -> Any:
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    return pick("input_tokens", "input"), pick("output_tokens", "output")


def report_envelope(
    stdout: str,
    *,
    root: Path,
    session_id: str,
    sender: str,
    capability: str,
    task: str,
    correlation_id: str,
    duration_ms: int,
) -> tuple[Path | None, str | None]:
    """Turn a finished print-mode run into one bus envelope.

    Returns `(path, None)` on success and `(None, reason)` when nothing could be
    recorded. Every refusal is a reason rather than an exception, because the
    caller still has to relay the child's own output and exit code.

    Nothing here invents envelope content. The summary, body, evidence, and next
    step come only from what the agent returned under the schema it was given; a
    run that returned nothing usable produces no record at all, because an
    invented summary is worse than a missing one.
    """
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return None, "the run produced no JSON on stdout"
    if not isinstance(result, dict):
        return None, "the run's JSON was not an object"

    payload = result.get("structured_output")
    if not isinstance(payload, dict):
        return None, "the run's JSON carried no structured_output object"

    tokens_in, tokens_out = usage_tokens(result)
    try:
        envelope = build_envelope(
            session_id=session_id,
            sender=sender,
            # The tier is recorded from what this process launched, never from
            # the agent's own claim. An envelope may describe its capability;
            # it may not choose one.
            capability=capability,
            kind=payload.get("kind"),
            summary=payload.get("summary", ""),
            body=payload.get("body"),
            evidence=payload.get("evidence"),
            next_step=payload.get("next"),
            task=task,
            # Empty means "none", not "the empty id": `normalize_trace` treats
            # any non-None value as a claim and validates it as a UUID.
            correlation_id=correlation_id or None,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return write_envelope(root, envelope), None
    except BusError as exc:
        return None, f"the structured output is not a valid envelope: {exc}"


def run_launch(
    argv: list[str],
    capability: str,
    *,
    report: bool = False,
    root: Path | None = None,
    session_id: str = "",
    sender: str = "",
    task: str = "",
    correlation_id: str = "",
) -> int:
    """Run a launch command, for the tiers where running it is the cheap path.

    The gate is `writes`, read from the shared tier table rather than from a
    second list here. A writing tier is refused with the command still printed,
    so a refusal hands the operator what they need instead of only a complaint.

    With `report`, the launcher also writes the bus envelope for the run. It
    does that because it is the only participant that can: a read-only tier has
    no `Write` tool, so the session cannot post its own record, and the duration
    and token counts belong to whoever held the subprocess rather than to the
    agent inside it. See `.ai/decisions/0002-session-substrate.md`.
    """
    if CAPABILITY_TIERS[capability]["writes"]:
        # Printed before print mode is applied, deliberately. This command is
        # for the operator to run, and `-p` would hand them a one-shot they
        # cannot converse with - which would make the refusal worse than a
        # refusal, rather than a refusal that leaves them equipped.
        print(" ".join(quote(item) for item in argv))
        fail(
            f"--exec refuses {capability} because this tier writes to the "
            "repository. The command is printed above; run it yourself, or "
            "dispatch a read-only tier instead."
        )

    binary = find_claude()
    if binary is None:
        fail("claude is not on PATH; cannot --exec")

    # Only a command this process is about to read needs to be parseable.
    argv = print_mode_argv(argv, schema=report)

    started = time.monotonic_ns()
    proc = subprocess.run(  # noqa: S603  (argv built from the tier table)
        [binary, *argv[1:]],
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    if not report:
        return proc.returncode

    if proc.returncode != 0:
        print(
            f"# no envelope: the run exited {proc.returncode}",
            file=sys.stderr,
        )
        return proc.returncode

    path, reason = report_envelope(
        proc.stdout,
        root=(root or Path(".")).resolve(),
        session_id=session_id,
        sender=sender,
        capability=capability,
        task=task,
        correlation_id=correlation_id,
        duration_ms=duration_ms,
    )
    if path is None:
        print(f"# no envelope: {reason}", file=sys.stderr)
        # The child succeeded but the loop did not close. Reporting zero here
        # would tell a caller the record exists.
        return 1

    root_path = (root or Path(".")).resolve()
    try:
        shown = path.relative_to(root_path).as_posix()
    except ValueError:  # pragma: no cover - the bus always writes under root
        shown = str(path)
    print(f"# envelope: {shown}", file=sys.stderr)
    return proc.returncode


def cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        entries = registry(root, include_done=True)
    except SessionError as exc:
        fail(str(exc))

    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("no sessions for this repository")
        return 0
    for entry in entries:
        marker = "live" if is_live(entry) else "done"
        print(
            f"[{marker}] {entry.get('id', '?')} {entry.get('kind', '?')} "
            f"- {str(entry.get('name', ''))[:80]}"
        )
    return 0


def printable(value: str) -> str:
    """Make text from another program safe to print on this console.

    Terminal titles are decorative text written by whatever is running in the
    tab: box drawing, emoji, and lone surrogates all appear. Windows consoles
    default to a regional code page - cp1254 on this machine - and printing an
    unencodable character there raises UnicodeEncodeError. Measured: `sweep`
    died mid-listing on a tab titled with a status glyph.

    A teardown check must not fail because a title was pretty.
    """
    encoding = sys.stdout.encoding or "utf-8"
    return value.encode(encoding, "replace").decode(encoding, "replace")


def orca_tabs(root: Path) -> list[dict[str, Any]]:
    """Claude agent tabs Orca reports for this repository, best effort.

    Foreground sessions in Orca tabs are invisible to the sweep below, which
    only looks at `kind == "background"`. Listing them closes that gap.

    It only *lists* them. The first version of this filtered on the title the
    launcher sets, and a live test showed why that cannot work: Claude Code
    rewrites its own terminal title from the conversation, so a tab created as
    `harness:reader:1bcf4ec4` was found again as `Orca_surface_live`. Orca
    exposes no join key back to a session id either, so nothing here can tell a
    harness-launched tab from the one the operator is reading this in.

    Closing on that basis would recreate, with a worse blast radius, the exact
    bug `is_self` exists to prevent: a teardown step that stops the session
    running it. So this reports, and the operator closes what they recognise.
    `agentIdentity` is Orca's own field and is not rewritten by the TUI.

    Best effort by design. Orca being absent, closed, or of a different version
    must not turn a teardown check into a failure.
    """
    binary = find_orca()
    if binary is None:
        return []
    try:
        proc = subprocess.run(  # noqa: S603  (fixed argv, no shell)
            [
                binary,
                "terminal",
                "list",
                "--worktree",
                f"path:{root}",
                "--json",
            ],
            capture_output=True,
            timeout=60,
            check=False,
            **ORCA_TEXT,
        )
        payload = json.loads(proc.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    if not payload.get("ok", False):
        return []
    terminals = (payload.get("result") or {}).get("terminals") or []
    return [
        item
        for item in terminals
        if isinstance(item, dict) and str(item.get("agentIdentity", "")) == "claude"
    ]


def cmd_sweep(args: argparse.Namespace) -> int:
    """Report, and optionally stop, background sessions left running here."""
    root = Path(args.root).resolve()
    try:
        entries = registry(root, include_done=False)
    except SessionError as exc:
        fail(str(exc))

    orphans = [
        entry
        for entry in entries
        if entry.get("kind") == "background" and is_live(entry) and not is_self(entry)
    ]

    tabs = orca_tabs(root)
    if tabs:
        print(f"{len(tabs)} Claude agent tab(s) open in Orca for this repository:")
        for tab in tabs:
            title = printable(str(tab.get("title", "")))[:70]
            print(f"  {tab.get('handle', '?')}  {title}")
        print(
            "  Listed, not swept. One of these is the tab you are reading this "
            "in, and nothing here can tell which, so close what you recognise "
            "with `orca terminal close --terminal <handle> --tab`."
        )
        print()

    if not orphans:
        print(
            "SWEEP CLEAN: no background sessions running for this repository "
            "(the session running this sweep is never counted)"
        )
        return 0

    for entry in orphans:
        print(
            f"  {entry.get('id', '?')}  {str(entry.get('name', ''))[:70]}  "
            f"(pid {entry.get('pid')})"
        )

    if not args.stop:
        print(
            f"\n{len(orphans)} background session(s) still running. "
            "This was a dry run; re-run with --stop to stop them."
        )
        return 1

    binary = find_claude()
    if not binary:
        fail("claude was not found on PATH")
    failures = 0
    for entry in orphans:
        identifier = str(entry.get("id", "")).strip()
        if not identifier:
            continue
        proc = subprocess.run(  # noqa: S603  (fixed argv, no shell)
            [binary, "stop", identifier],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0:
            print(f"stopped {identifier}")
        else:
            failures += 1
            print(f"could not stop {identifier}: {proc.stderr.strip()}", file=sys.stderr)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch specifications and teardown for harness agent sessions."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    launch = sub.add_parser(
        "launch",
        help="Print, or with --exec run, the command that launches a session.",
        description=(
            "Prints the command by default. --exec runs it, and only for a tier "
            "that cannot write; starting something that changes the repository "
            "stays the operator's action."
        ),
    )
    launch.add_argument("--capability", required=True, choices=sorted(CAPABILITY_TIERS))
    launch.add_argument("--task", required=True, help="The prompt for the session")
    launch.add_argument("--session-id", help="Session UUID (default: generate one)")
    launch.add_argument(
        "--background", action="store_true", help="Detach with --bg (writing tiers only)"
    )
    launch.add_argument("--worktree", help="Worktree name for a writing tier")
    launch.add_argument(
        "--scope", action="append", default=[], help="Writable directory (repeatable)"
    )
    launch.add_argument(
        "--restricted",
        action="store_true",
        help=(
            "Also ignore user, project, and local settings files. Use when the "
            "repository is untrusted: its .claude/settings.json is repository "
            "text, and repository text must not become tool permissions."
        ),
    )
    launch.add_argument(
        "--surface",
        choices=SESSION_SURFACES,
        default="inproc",
        help=(
            "Where the session runs. inproc (default) is this process. orca "
            "places the same tier-enforced command in a visible Orca terminal "
            "tab, and delivers the prompt as terminal input."
        ),
    )
    launch.add_argument(
        "--lane",
        help=(
            "Orca worktree name for a writing tier. Orca creates the checkout, "
            "so `claude --worktree` is dropped and not nested inside it."
        ),
    )
    launch.add_argument("--json", action="store_true", help="Emit argv as JSON")
    launch.add_argument("--root", default=".", help="Repository root (default: .)")
    launch.add_argument(
        "--correlation",
        help=(
            "UUID grouping this dispatch with the other sessions serving the "
            "same unit of work. Reported on stderr; --report mints one when "
            "it is omitted."
        ),
    )
    launch.add_argument(
        "--report",
        action="store_true",
        help=(
            "After an --exec run, write its bus envelope. Read-only tiers on "
            "the inproc surface only: a read-only session has no Write tool to "
            "post its own record, and the duration and token counts belong to "
            "this process rather than to the agent."
        ),
    )
    launch.add_argument(
        "--report-from",
        help="Sender name on the written envelope (default: the tier name)",
    )
    launch.add_argument(
        "--exec",
        dest="execute",
        action="store_true",
        help=(
            "Run the command instead of printing it. On the inproc surface, "
            "read-only tiers only. On the orca surface a writing tier is also "
            "allowed, because --lane confines it to its own checkout and the "
            "tab keeps it in view."
        ),
    )
    launch.set_defaults(func=cmd_launch)

    listing = sub.add_parser("list", help="List sessions started under this repository.")
    listing.add_argument("--root", default=".", help="Repository root (default: .)")
    listing.add_argument("--json", action="store_true", help="Emit the raw registry")
    listing.set_defaults(func=cmd_list)

    sweep = sub.add_parser(
        "sweep",
        help="Find background sessions left running here. Dry-run unless --stop.",
    )
    sweep.add_argument("--root", default=".", help="Repository root (default: .)")
    sweep.add_argument("--stop", action="store_true", help="Actually stop them")
    sweep.set_defaults(func=cmd_sweep)

    args = parser.parse_args()
    if args.command == "launch" and not args.session_id:
        args.session_id = str(uuid.uuid4())
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

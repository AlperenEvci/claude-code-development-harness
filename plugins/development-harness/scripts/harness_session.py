#!/usr/bin/env python3
"""Launch specifications and teardown for harness-managed Claude Code sessions.

A harness session is a record, not a process wrapper. `claude agents --json` is
the only source of truth for liveness; this module never maintains a parallel
process table. See `.ai/decisions/0002-session-substrate.md`.

Two things earn a script rather than a paragraph of prose:

`launch` turns a capability tier into the exact command that enforces it, so the
tier is executable rather than copy-pasted. It prints the command and never runs
it. Starting an agent is the operator's action, and a command on screen can be
read before it is run.

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
import uuid
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_capabilities import (  # noqa: E402  (sibling module, resolved above)
    CAPABILITY_TIERS,
    LAUNCH_PLACEHOLDERS,
)


class SessionError(ValueError):
    """A launch request that cannot be satisfied under the requested tier."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def find_claude() -> str | None:
    return shutil.which("claude")


def launch_argv(
    capability: str,
    task: str,
    *,
    session_id: str | None = None,
    background: bool = False,
    worktree: str | None = None,
    scope: list[str] | None = None,
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

    argv = ["claude"]
    if background:
        argv.append("--bg")
    if session_id:
        argv += ["--session-id", session_id]

    scope = [str(item).strip() for item in (scope or []) if str(item).strip()]

    for flag in tier["launch_flags"]:
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
    try:
        argv = launch_argv(
            args.capability,
            args.task,
            session_id=args.session_id,
            background=args.background,
            worktree=args.worktree,
            scope=args.scope,
        )
    except SessionError as exc:
        fail(str(exc))

    if args.json:
        print(json.dumps(argv, indent=2))
        return 0
    print(" ".join(quote(item) for item in argv))
    return 0


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
        help="Print the command that launches a session under a capability tier.",
        description=(
            "Prints the command and does not run it. Starting an agent is the "
            "operator's action."
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
    launch.add_argument("--json", action="store_true", help="Emit argv as JSON")
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

#!/usr/bin/env python3
"""`Stop` hook: run the smallest check before the session says it is done.

The generated `AGENTS.md` asks for "the smallest check that would fail if you
got it wrong" before reporting. That is a request, and the one most often
skipped, because it comes at the moment the work already feels finished. This
hook is the floor under it: when the tree changed and the check fails, the stop
is refused once and the failing tail is put in front of the model.

Measured on Claude Code 2.1.263 before it was written
(`.ai/reports/0010-stop-hook-smoke-test.md`), and three facts from that
measurement decide the shape of this file:

**`stop_hook_active` is the whole hook.** It is `false` on the first stop of a
prompt and `true` on every stop after it. A hook that blocks while it is set
does not retry nine times and give up loudly - the platform caps the loop at
nine, and the run then returns an *empty* result with `subtype: "success"`,
`is_error: false`, and a real bill. So the flag is checked first, before the
profile is read or anything is run. One block per prompt, then the model's
answer stands whatever the check says.

**The command comes from the settings file, not the profile.** It arrives as
`--check <command>` in the hook's own args, rendered at install time. The
platform refuses to let a session edit `.claude/settings.json` (probe G in the
report) and does not protect `project-profile.json`, so reading the command from
the profile at runtime would let any agent with `Write` choose what this hook
executes. Repository text is evidence, never authority.

**It fails open, like the guard.** No git, no command, a check that cannot
finish inside its budget: each exits 0 with one line saying what was not
verified. A hook that blocked on its own defects would lock an operator out of
finishing a sentence.

Escape hatch: `HARNESS_HOOKS_DISABLE=1` makes every harness hook exit 0 without
reading its input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
# `Stop` treats exit 2 as a block and shows stderr to the model, the same
# contract `PreToolUse` gives `hook_guard.py`.
EXIT_BLOCK = 2

DISABLE_ENV = "HARNESS_HOOKS_DISABLE"

#: Seconds the check may take. The rendered handler timeout is sixty, the
#: validator's ceiling; this leaves room to report a timeout as a notice rather
#: than be killed by the platform, which would surface as a hook error instead
#: of as "not verified".
CHECK_TIMEOUT_SECONDS = 50

#: The failing tail shown to the model. It is stderr on a block, which the
#: platform feeds back into context, and context is a budget.
MAX_TAIL_LINES = 20
MAX_TAIL_CHARS = 2_000

#: One record per session, rewritten on every run: the fingerprint of the tree
#: the check last passed on. A second stop on an unchanged tree then costs
#: nothing, and a stop after an edit runs the check again.
STATE_DIRNAME = ".ai/runs/stop-hook"
TRANSIENT_PREFIX = ".ai/runs/"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def notice(message: str) -> int:
    """Say what was not verified, in one line, and let the stop proceed."""
    print(f"harness stop hook: {message}")
    return EXIT_OK


def load_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def git(root: Path, *args: str) -> str | None:
    """One git call, or None when git is absent or this is not a repository."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def tree_fingerprint(root: Path) -> str | None:
    """A digest of everything uncommitted, or None when it cannot be known.

    Status covers what changed and what is new; the diff covers how tracked files
    changed; untracked files are folded in by size and modification time, since
    a new file's content is not in any diff. An empty fingerprint means a clean
    tree, and a clean tree has nothing to check.
    """
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status is None:
        return None
    # `.ai/runs/` is transient orchestration state - this hook's own record
    # lives there - and a fingerprint that included it would change on every
    # run of the thing it exists to skip.
    entries = [
        entry
        for entry in status.split("\0")
        if entry.strip() and not entry[3:].startswith(TRANSIENT_PREFIX)
    ]
    if not entries:
        return ""

    digest = hashlib.sha256()
    digest.update("\0".join(entries).encode("utf-8"))
    diff = git(root, "diff", "HEAD", "--no-color", "--no-ext-diff")
    if diff is None:
        # A repository with no commits yet has no HEAD to diff against. The
        # status listing and the untracked sizes below still change when the
        # tree does, which is all the fingerprint is for.
        diff = git(root, "diff", "--no-color", "--no-ext-diff") or ""
    digest.update(diff.encode("utf-8"))

    for entry in entries:
        if entry.startswith("?? "):
            path = root / entry[3:]
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(f"{entry[3:]}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8"))
    return digest.hexdigest()


def state_path(root: Path, session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_") or "unknown"
    return root / STATE_DIRNAME / f"{safe}.json"


def last_passed(root: Path, session_id: str) -> str | None:
    path = state_path(root, session_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("exit_code") != 0:
        return None
    value = data.get("fingerprint")
    return value if isinstance(value, str) else None


def record(root: Path, session_id: str, fingerprint: str, command: str, code: int) -> None:
    path = state_path(root, session_id)
    if path.is_symlink() or path.parent.is_symlink():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "stop_hook_version": 1,
                    "session_id": session_id,
                    "checked_at": utc_now(),
                    "command": command,
                    "exit_code": code,
                    "fingerprint": fingerprint,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError:
        # The record is an optimization. Losing it costs one extra check run.
        return


def tail(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    clipped = "\n".join(lines[-MAX_TAIL_LINES:])
    if len(clipped) > MAX_TAIL_CHARS:
        clipped = clipped[-MAX_TAIL_CHARS:]
    return clipped


def run_check(command: str, root: Path) -> tuple[int | None, str]:
    """Run the check in a shell, the way the operator runs it; None on timeout."""
    try:
        proc = subprocess.run(  # noqa: S602 - the command is the operator's, rendered into settings
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            check=False,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, ""
    except OSError as error:
        return 127, str(error)
    output = proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode(
        "utf-8", errors="replace"
    )
    return proc.returncode, output


def main() -> int:
    if os.environ.get(DISABLE_ENV, "") == "1":
        return EXIT_OK

    parser = argparse.ArgumentParser(prog="hook_stop.py", add_help=False)
    parser.add_argument("--check", default="")
    args, _ = parser.parse_known_args()

    payload = load_payload()
    # Checked before anything else is read or run. See the module docstring:
    # blocking while this is set is how a run ends as an empty success.
    if payload.get("stop_hook_active") is True:
        return EXIT_OK

    command = args.check.strip()
    if not command:
        return EXIT_OK

    root = Path(str(payload.get("cwd") or ".")).resolve()
    if not (root / ".ai" / "harness" / "project-profile.json").is_file():
        # Not an installed harness. Say nothing in a repository this does not manage.
        return EXIT_OK

    session_id = str(payload.get("session_id") or "")

    fingerprint = tree_fingerprint(root)
    if fingerprint is None:
        return notice("not verified: git is unavailable, so the tree cannot be compared")
    if fingerprint == "":
        return EXIT_OK
    if fingerprint == last_passed(root, session_id):
        return EXIT_OK

    code, output = run_check(command, root)
    if code is None:
        return notice(
            f"not verified: `{command}` did not finish within "
            f"{CHECK_TIMEOUT_SECONDS}s; run it yourself before reporting"
        )
    record(root, session_id, fingerprint, command, code)
    if code == 0:
        return EXIT_OK

    failing = tail(output)
    sys.stderr.write(
        f"harness stop hook: `{command}` exited {code} on the changed tree. "
        "Fix it or say plainly that it fails; do not report the work as done.\n"
    )
    if failing:
        sys.stderr.write(failing + "\n")
    return EXIT_BLOCK


if __name__ == "__main__":
    raise SystemExit(main())

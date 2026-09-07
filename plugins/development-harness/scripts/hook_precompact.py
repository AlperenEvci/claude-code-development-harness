#!/usr/bin/env python3
"""`PreCompact` hook: write the record down before the transcript is truncated.

Compaction is the one moment a session reliably loses its own history, and it is
also the one moment nobody is present to type a handoff - it happens between
turns, unannounced, while the operator is reading something else. Every release
before this one answered that with a rule in `AGENTS.md` telling the model to
checkpoint at the ceiling. This is the mechanism that rule was standing in for.

Three things about the payload shape what this file can honestly do, all measured
on Claude Code 2.1.263 (`.ai/reports/0006-compaction-smoke-test.md`):

- It carries a `session_id`, a `transcript_path`, a `cwd`, and a `trigger`. There
  is no summary and no token count, so nothing here writes an intent: a record
  that guesses what the session was doing is worse than one that says only what
  it knows.
- `transcript_path` is not opened. That file holds whatever the session read,
  including files the engineering contract forbids copying into a durable
  artifact, and a hook that reads it to write a nicer summary has quietly become
  the exfiltration path it was supposed to guard.
- Compaction is not once per session. One 51-turn run compacted three times, each
  `PreCompact` paired with a `SessionStart` carrying `source: "compact"`. So the
  record is a per-session boundary log that folds, not a new directory each time.

It never blocks. `PreCompact` cannot stop a compaction that is already necessary,
and a non-zero exit here would only put an error in front of the operator at the
moment the session is least able to explain itself. Every path returns 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
DISABLE_ENV = "HARNESS_HOOKS_DISABLE"

#: The boundary log is written by a subprocess rather than an import, unlike the
#: session brief. `harness_checkpoint.py` owns the record's shape and its symlink
#: refusal, and `from-hook` is that ownership expressed as a command; importing it
#: here would put a second caller inside the module's internals for no gain.
CHECKPOINT_SCRIPT = "harness_checkpoint.py"

#: A hook has a timeout, and the work is one JSON read and one JSON write. If it
#: has not finished well inside this, something is wrong that waiting will not fix.
TIMEOUT_SECONDS = 15


def notice(message: str) -> int:
    """Say what went wrong in one line, and let the compaction proceed."""
    print(f"harness: compaction boundary not recorded ({message})", file=sys.stderr)
    return EXIT_OK


def main() -> int:
    if os.environ.get(DISABLE_ENV, "") == "1":
        return EXIT_OK

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    root = Path(str(payload.get("cwd") or ".")).resolve()
    if not (root / ".ai" / "harness" / "project-profile.json").is_file():
        # Not an installed harness. A hook that announces itself in a repository
        # it does not manage is noise.
        return EXIT_OK

    script = Path(__file__).resolve().parent / CHECKPOINT_SCRIPT
    if not script.is_file():
        return notice(f"{CHECKPOINT_SCRIPT} is not installed beside this hook")

    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(script), "--root", str(root), "from-hook"],
            input=raw,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return notice(f"{CHECKPOINT_SCRIPT} did not finish in {TIMEOUT_SECONDS}s")
    except OSError as error:
        return notice(f"{type(error).__name__}: {error}")

    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        return notice(detail[-1] if detail else f"exit {result.returncode}")

    line = (result.stdout or "").strip()
    if line:
        print(line)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

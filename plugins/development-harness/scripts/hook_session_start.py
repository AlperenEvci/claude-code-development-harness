#!/usr/bin/env python3
"""`SessionStart` hook: put the brief in front of the session, not in its way.

1.12.0 replaced a three-command session-start checklist with one command,
`harness_report.py --brief`, and said plainly why: a checklist of three is three
chances to skip one. One command is one chance. This hook is the last step of
that argument - the brief is printed by the harness at session start, so nobody
has to remember it.

Stdout from a `SessionStart` hook is added to the session's context, which is why
the output here is capped. Two further facts about that context, both from the
platform's own documentation, shape this file:

- hook-added context is **summarized away** by compaction, so the `compact`
  matcher re-runs this hook and prints the brief again;
- a `SessionStart` hook that fails is noise at the worst moment, so every failure
  here exits 0 with one line of explanation rather than a stack trace.

It reads. It never writes, never runs a subprocess, and never blocks a session.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
DISABLE_ENV = "HARNESS_HOOKS_DISABLE"

# The brief is context, and context is a budget. A ledger with a hundred pending
# items would otherwise open every session by spending thousands of tokens on a
# list nobody reads to the end. The truncation notice names the command that
# prints the rest.
MAX_BRIEF_CHARS = 3_000

sys.path.insert(0, str(Path(__file__).resolve().parent))


def notice(message: str) -> int:
    """Say what went wrong in one line, and let the session start anyway."""
    print(f"harness: session brief unavailable ({message})")
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
        # Not an installed harness. Say nothing: a hook that announces itself in
        # a repository it does not manage is noise.
        return EXIT_OK

    try:
        import harness_report
    except ImportError as error:  # pragma: no cover - defensive
        return notice(f"harness_report.py is not importable: {error}")

    try:
        model = harness_report.build_model(root)
        text = harness_report.render_brief(model)
    except Exception as error:  # noqa: BLE001 - a brief must never break a session
        return notice(f"{type(error).__name__}: {error}")

    if len(text) > MAX_BRIEF_CHARS:
        text = (
            text[:MAX_BRIEF_CHARS].rstrip()
            + f"\n... truncated at {MAX_BRIEF_CHARS} characters; "
            "run `harness_report.py --brief` for the rest"
        )

    source = str(payload.get("source") or "")
    if source == "compact":
        # Compaction summarizes hook-added context away, so this is a reprint
        # rather than news. Saying so stops the model treating it as a change.
        print("harness: reprinting the session brief after compaction")
    print(text)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

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

It reads, and it never blocks a session. Since 1.19.0 it may also run one
thing: the profile's smoke command, when the rendered settings pass it as
`--smoke <command>`. The command arrives in the hook's own args rather than
being read from the profile at runtime, because the platform refuses to let a
session edit `.claude/settings.json` and does not protect
`project-profile.json` - so the settings file is the one place an executed
string cannot be planted by an agent with `Write`
(`.ai/reports/0010-stop-hook-smoke-test.md`, probes G and H). The result is
one line, pass or fail, and a smoke that cannot finish inside its budget is
reported as not run rather than as either.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

EXIT_OK = 0
DISABLE_ENV = "HARNESS_HOOKS_DISABLE"

# The brief is context, and context is a budget. A ledger with a hundred pending
# items would otherwise open every session by spending thousands of tokens on a
# list nobody reads to the end. The truncation notice names the command that
# prints the rest.
MAX_BRIEF_CHARS = 3_000

#: Seconds the smoke command may take. The handler timeout is twenty; a smoke
#: that needs longer is a test suite, and belongs in the Stop hook's check or in
#: the full gate, not in front of every session.
SMOKE_TIMEOUT_SECONDS = 15
MAX_SMOKE_LINE_CHARS = 300

sys.path.insert(0, str(Path(__file__).resolve().parent))


def notice(message: str) -> int:
    """Say what went wrong in one line, and let the session start anyway."""
    print(f"harness: session brief unavailable ({message})")
    return EXIT_OK


def smoke_line(command: str, root: Path) -> str:
    """Run the smoke command and describe the outcome in one line.

    Pass, fail with the exit code and the last line of output, or not run. The
    three are kept distinct on purpose: a timeout reported as a failure would
    send the model chasing a defect that is not there, and reported as a pass
    would be a lie.
    """
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S602 - the operator's command, rendered into settings
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            check=False,
            timeout=SMOKE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (
            f"SMOKE  not run: `{command}` did not finish within "
            f"{SMOKE_TIMEOUT_SECONDS}s"
        )
    except OSError as error:
        return f"SMOKE  not run: `{command}` could not start ({error})"
    elapsed = time.monotonic() - started
    if proc.returncode == 0:
        return f"SMOKE  pass  `{command}` ({elapsed:.1f}s)"
    output = (
        proc.stdout.decode("utf-8", errors="replace")
        + proc.stderr.decode("utf-8", errors="replace")
    )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    last = lines[-1] if lines else "no output"
    return (
        f"SMOKE  FAIL exit {proc.returncode}  `{command}`  last: {last}"
    )[:MAX_SMOKE_LINE_CHARS]


def main() -> int:
    if os.environ.get(DISABLE_ENV, "") == "1":
        return EXIT_OK

    parser = argparse.ArgumentParser(prog="hook_session_start.py", add_help=False)
    parser.add_argument("--smoke", default="")
    args, _ = parser.parse_known_args()

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

    smoke = args.smoke.strip()
    if smoke and source != "compact":
        # Not re-run after compaction: nothing about the tree changed because
        # the transcript was truncated, and a smoke run costs seconds of a
        # moment the model is already recovering from.
        print(smoke_line(smoke, root))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

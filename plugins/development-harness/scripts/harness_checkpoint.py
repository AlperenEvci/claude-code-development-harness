#!/usr/bin/env python3
"""Measure the context budget against the declared policy, and record a handoff.

`context_policy` has been in the project profile since 0.6, and until now nothing
read it. The band was rendered into `AGENTS.md`, the validator confirmed the
rendered prose matched the profile, and that was the whole mechanism: two
descriptions of an intention agreeing with each other. An agent could run to the
edge of its window without anything noticing, because nothing was measuring.

This module is the missing half. `.ai/harness/project-profile.json` is installed
in every harnessed repository and already carries the normalized policy, so the
band is data, not prose, and can be compared against a number.

What it cannot do is read the number itself. Nothing running as a subprocess can
observe the context window of the session that spawned it, and pretending
otherwise would put a fabricated measurement where a real one belongs. So `used`
is supplied by the caller and this module owns the two things it can be honest
about: the decision the policy implies, and the record that survives the session.

`status` compares a reported token count against the band and names the action
the profile declares. It exits 3 at or over the ceiling, so a caller can branch
on the policy without parsing prose.

`write` records a handoff under `.ai/runs/`, on the shape the long-context
literature converges on: what the session was trying to do, what it produced, and
what the next session must do first. It refuses a checkpoint with no next step.
A handoff whose next step is missing is the failure it was written to prevent -
the reader gets a summary and still has to reconstruct the plan.

Artifacts are recorded as paths and never as contents. A changed-file list is
evidence about where the work landed; the contents of those files are what the
engineering contract forbids copying into a durable artifact, because one of them
is eventually a `.env`.

`resume` prints the most recent checkpoint, so a fresh session starts from the
record rather than from what someone remembers of the transcript.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

CHECKPOINT_VERSION = 1

#: Defaults mirror render_harness.normalize_context_policy, so a repository whose
#: profile predates `context_policy` still gets a working band rather than an
#: error. Kept in step by a test.
DEFAULT_FLOOR_TOKENS = 150_000
DEFAULT_CEILING_TOKENS = 200_000
DEFAULT_ON_CEILING = "checkpoint-and-handoff"

ALLOWED_CEILING_ACTIONS = {"compact", "checkpoint-and-handoff", "stop-and-ask"}

#: What the caller is told to do at the ceiling. The wording is the profile's
#: decision, not this module's opinion.
CEILING_ACTION_TEXT = {
    "compact": "compact the conversation, then continue from the compacted state.",
    "checkpoint-and-handoff": (
        "write a checkpoint and hand off to a fresh session or an isolated agent. "
        "Do not keep accumulating."
    ),
    "stop-and-ask": (
        "stop and ask the operator how to proceed. Do not silently continue past "
        "the budget."
    ),
}

#: Caps exist for the same reason the bus has them: a checkpoint is read into a
#: fresh session's context, so an unbounded one recreates the problem it exists
#: to solve.
MAX_INTENT_CHARS = 2_000
MAX_STEP_CHARS = 500
MAX_STEPS = 20
MAX_ARTIFACTS = 100
MAX_NOTE_CHARS = 4_000

#: Exit code for "the ceiling was reached". Distinct from a usage error so a
#: caller can branch on the policy without reading stdout.
EXIT_CEILING = 3

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
RUN_DIR_PATTERN = re.compile(r"\A\d{8}T\d{6}Z-[a-z0-9-]+\Z")


class CheckpointError(ValueError):
    """A checkpoint that cannot be written as asked."""


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text: str, *, fallback: str = "checkpoint") -> str:
    slug = SLUG_PATTERN.sub("-", text.strip().lower()).strip("-")
    slug = "-".join(slug.split("-")[:6])[:48].strip("-")
    return slug or fallback


def read_policy(root: Path) -> dict[str, Any]:
    """Load the installed policy, falling back to the documented defaults.

    A missing profile is not an error. This script is useful in a repository
    whose harness predates `context_policy`, and refusing to run there would mean
    the only tool that can record a handoff is unavailable exactly when someone
    is trying to hand off.
    """
    path = root / ".ai" / "harness" / "project-profile.json"
    policy: dict[str, Any] = {}
    if path.is_file():
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CheckpointError(f"cannot read {path}: {error}") from error
        if isinstance(profile, dict) and isinstance(profile.get("context_policy"), dict):
            policy = profile["context_policy"]

    band = policy.get("working_band") if isinstance(policy.get("working_band"), dict) else {}
    floor = band.get("floor_tokens", DEFAULT_FLOOR_TOKENS)
    ceiling = band.get("ceiling_tokens", DEFAULT_CEILING_TOKENS)
    if not isinstance(floor, int) or not isinstance(ceiling, int) or floor >= ceiling:
        raise CheckpointError(
            "context_policy.working_band is malformed: floor_tokens must be an "
            "integer below ceiling_tokens"
        )

    action = str(policy.get("on_ceiling", DEFAULT_ON_CEILING)).strip().lower()
    if action not in ALLOWED_CEILING_ACTIONS:
        raise CheckpointError(
            f"context_policy.on_ceiling is {action!r}; expected one of "
            f"{sorted(ALLOWED_CEILING_ACTIONS)}"
        )

    return {
        "floor_tokens": floor,
        "ceiling_tokens": ceiling,
        "on_ceiling": action,
        "source": str(path) if path.is_file() else "defaults (no installed profile)",
    }


def zone_for(used: int, floor: int, ceiling: int) -> str:
    if used >= ceiling:
        return "at-ceiling"
    if used >= floor:
        return "in-band"
    return "below-floor"


def changed_paths(root: Path) -> list[str]:
    """Paths git reports as changed, as evidence of where the work landed.

    Read-only and best-effort. A repository without git, or without a work tree,
    simply contributes nothing here rather than failing the checkpoint.
    """
    if shutil.which("git") is None:
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    paths: list[str] = []
    for line in result.stdout.splitlines():
        entry = line[3:].strip() if len(line) > 3 else ""
        if " -> " in entry:  # a rename reports both sides; the new path is the artifact
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip('"')
        if entry:
            paths.append(entry)
    return paths


def bounded(items: list[str], limit: int, label: str) -> list[str]:
    cleaned = [item.strip() for item in items if item.strip()]
    if len(cleaned) > limit:
        raise CheckpointError(f"{label} has {len(cleaned)} entries, limit is {limit}")
    return cleaned


def build_checkpoint(
    *,
    intent: str,
    next_steps: list[str],
    artifacts: list[str],
    derived: list[str],
    note: str | None,
    used: int | None,
    policy: dict[str, Any],
    stamp: datetime,
) -> dict[str, Any]:
    intent = intent.strip()
    if not intent:
        raise CheckpointError("intent is required: state what this session was trying to do")
    if len(intent) > MAX_INTENT_CHARS:
        raise CheckpointError(
            f"intent is {len(intent)} characters, limit is {MAX_INTENT_CHARS}"
        )

    steps = bounded(next_steps, MAX_STEPS, "next steps")
    if not steps:
        # The whole point of the record. A checkpoint without one is a summary,
        # and the next session still has to work out what to do.
        raise CheckpointError(
            "at least one --next step is required: a handoff with no next step "
            "leaves the reader to reconstruct the plan"
        )
    for step in steps:
        if len(step) > MAX_STEP_CHARS:
            raise CheckpointError(
                f"a next step is {len(step)} characters, limit is {MAX_STEP_CHARS}"
            )

    merged: list[str] = []
    for path in bounded(artifacts, MAX_ARTIFACTS, "artifacts") + derived:
        if path not in merged:
            merged.append(path)
    if len(merged) > MAX_ARTIFACTS:
        merged = merged[:MAX_ARTIFACTS]

    if note is not None and len(note) > MAX_NOTE_CHARS:
        raise CheckpointError(f"note is {len(note)} characters, limit is {MAX_NOTE_CHARS}")

    record: dict[str, Any] = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "created_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "intent": intent,
        "artifacts": merged,
        "next_steps": steps,
        "policy": {
            "floor_tokens": policy["floor_tokens"],
            "ceiling_tokens": policy["ceiling_tokens"],
            "on_ceiling": policy["on_ceiling"],
        },
    }
    if used is not None:
        record["context"] = {
            "reported_used_tokens": used,
            "zone": zone_for(used, policy["floor_tokens"], policy["ceiling_tokens"]),
            "measured_by": "caller-reported",
        }
    if note:
        record["note"] = note.strip()
    return record


def render_markdown(record: dict[str, Any]) -> str:
    lines = [
        "# Checkpoint",
        "",
        f"Written {record['created_at']}.",
        "",
        "## Intent",
        "",
        record["intent"],
        "",
        "## Artifacts",
        "",
    ]
    if record["artifacts"]:
        lines += [f"- `{path}`" for path in record["artifacts"]]
    else:
        lines.append("None recorded.")
    lines += ["", "## Next steps", ""]
    lines += [f"{index}. {step}" for index, step in enumerate(record["next_steps"], 1)]

    context = record.get("context")
    if context:
        lines += [
            "",
            "## Context at checkpoint",
            "",
            f"Reported {context['reported_used_tokens']} tokens used "
            f"({context['zone']}), against a "
            f"{record['policy']['floor_tokens']}-{record['policy']['ceiling_tokens']} "
            "token band. The figure is caller-reported: nothing here measured it.",
        ]
    if record.get("note"):
        lines += ["", "## Note", "", record["note"]]
    return "\n".join(lines) + "\n"


def refuse_symlinks(path: Path, root: Path) -> None:
    """Refuse to write through a symlink, the way the installer does.

    A symlinked `.ai/runs` would place the record somewhere the operator did not
    choose, which for a durable artifact is worse than not writing it.
    """
    current = path
    while current != root and current.parent != current:
        if current.is_symlink():
            raise CheckpointError(f"refusing to write through a symlink: {current}")
        current = current.parent


def write_checkpoint(root: Path, record: dict[str, Any], label: str | None) -> Path:
    stamp = record["created_at"].replace("-", "").replace(":", "")
    slug = slugify(label or record["intent"])
    directory = root / ".ai" / "runs" / f"{stamp}-{slug}"
    refuse_symlinks(directory.parent, root)
    if directory.exists():
        raise CheckpointError(f"checkpoint directory already exists: {directory}")
    directory.mkdir(parents=True)

    text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    (directory / "checkpoint.json").write_text(text, encoding="utf-8", newline="\n")
    (directory / "checkpoint.md").write_text(
        render_markdown(record), encoding="utf-8", newline="\n"
    )
    return directory


def latest_checkpoint(root: Path) -> Path | None:
    runs = root / ".ai" / "runs"
    if not runs.is_dir():
        return None
    candidates = [
        path / "checkpoint.json"
        for path in runs.iterdir()
        if path.is_dir() and RUN_DIR_PATTERN.match(path.name)
    ]
    existing = sorted(path for path in candidates if path.is_file())
    return existing[-1] if existing else None


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    policy = read_policy(root)
    used = args.used
    zone = zone_for(used, policy["floor_tokens"], policy["ceiling_tokens"])
    action = CEILING_ACTION_TEXT[policy["on_ceiling"]]

    if args.json:
        print(json.dumps({
            "reported_used_tokens": used,
            "zone": zone,
            **{key: policy[key] for key in ("floor_tokens", "ceiling_tokens", "on_ceiling")},
            "policy_source": policy["source"],
        }, indent=2))
    else:
        band = f"{policy['floor_tokens']}-{policy['ceiling_tokens']}"
        print(f"reported: {used} tokens")
        print(f"band:     {band} ({zone})")
        print(f"policy:   {policy['on_ceiling']} (from {policy['source']})")
        if zone == "at-ceiling":
            print(f"action:   {action}")
        elif zone == "in-band":
            print("action:   none yet; you are inside the working band.")
        else:
            print("action:   none; below the working floor.")

    return EXIT_CEILING if zone == "at-ceiling" else 0


def command_write(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    policy = read_policy(root)
    derived = [] if args.no_git else changed_paths(root)
    record = build_checkpoint(
        intent=args.intent,
        next_steps=list(args.next or []),
        artifacts=list(args.artifact or []),
        derived=derived,
        note=args.note,
        used=args.used,
        policy=policy,
        stamp=now(),
    )
    directory = write_checkpoint(root, record, args.label)
    print(f"wrote {directory / 'checkpoint.md'}")
    print(f"wrote {directory / 'checkpoint.json'}")
    return 0


def command_resume(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = latest_checkpoint(root)
    if path is None:
        print("no checkpoint found under .ai/runs/", file=sys.stderr)
        return 1
    if args.json:
        print(path.read_text(encoding="utf-8").rstrip())
    else:
        markdown = path.with_name("checkpoint.md")
        print(f"# {path.parent.name}\n")
        print((markdown if markdown.is_file() else path).read_text(encoding="utf-8").rstrip())
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness_checkpoint.py",
        description=(
            "Compare reported context use against the declared policy, and record "
            "a handoff under .ai/runs/."
        ),
    )
    parser.add_argument("--root", default=".", help="Repository root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser(
        "status",
        help="Compare a reported token count against the profile's working band.",
    )
    status.add_argument(
        "--used",
        type=int,
        required=True,
        help=(
            "Tokens currently in the working context. Caller-reported: no "
            "subprocess can observe the window of the session that spawned it."
        ),
    )
    status.add_argument("--json", action="store_true", help="Emit JSON.")
    status.set_defaults(handler=command_status)

    write = sub.add_parser("write", help="Write a handoff checkpoint under .ai/runs/.")
    write.add_argument("--intent", required=True, help="What this session was trying to do.")
    write.add_argument(
        "--next",
        action="append",
        required=True,
        help="A next step for whoever picks this up. Repeatable; at least one.",
    )
    write.add_argument(
        "--artifact",
        action="append",
        help="A path this session produced. Repeatable. Paths only, never contents.",
    )
    write.add_argument("--note", help="Anything else the next session needs.")
    write.add_argument("--used", type=int, help="Reported tokens used, if known.")
    write.add_argument("--label", help="Slug for the run directory (default: from intent).")
    write.add_argument(
        "--no-git",
        action="store_true",
        help="Do not derive changed paths from git status.",
    )
    write.set_defaults(handler=command_write)

    resume = sub.add_parser("resume", help="Print the most recent checkpoint.")
    resume.add_argument("--json", action="store_true", help="Emit the raw record.")
    resume.set_defaults(handler=command_resume)

    args = parser.parse_args()
    try:
        raise SystemExit(args.handler(args))
    except CheckpointError as error:
        fail(str(error))


if __name__ == "__main__":
    main()

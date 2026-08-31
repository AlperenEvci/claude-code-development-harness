#!/usr/bin/env python3
"""Capability tiers for generated project agents.

One table, imported by the renderer, the validator, and the installed-harness
checker. Duplicating it would let the thing that writes authority and the thing
that checks authority drift apart, which is the failure this module exists to
prevent.

`reader` is the default and reproduces the pre-1.0 read-only agent exactly.
Raising a tier is deliberate, and `implementer` additionally requires a declared
writable scope and a recorded operator approval.

The launch flags matter as much as the frontmatter: a tier the process enforces
is a boundary, while a tier only declared in a file is a promise the agent could
ignore. See `.ai/decisions/0002-session-substrate.md`.
"""

from __future__ import annotations

from typing import Any

CAPABILITY_TIERS: dict[str, dict[str, Any]] = {
    "reader": {
        "tools": ["Read", "Grep", "Glob"],
        "disallowed": ["Write", "Edit", "Bash"],
        "permission_mode": "plan",
        "writes": False,
        "launch_flags": ["--permission-mode", "plan", "--tools", "Read,Grep,Glob"],
        "role": "a read-only project-domain researcher",
        "duties": [
            "Gather evidence; do not implement or edit.",
            "Do not run shell commands or access the network.",
        ],
    },
    "verifier": {
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "disallowed": ["Write", "Edit"],
        "permission_mode": "plan",
        "writes": False,
        "launch_flags": ["--permission-mode", "plan", "--tools", "Read,Grep,Glob,Bash"],
        "role": "an independent verifier",
        "duties": [
            "Run the configured gates and inspect the diff; do not edit files.",
            "Report findings with evidence. Do not fix what you find.",
            "Never weaken a gate or broaden permissions to make a check pass.",
        ],
    },
    "implementer": {
        "tools": ["Read", "Grep", "Glob", "Edit", "Write", "Bash"],
        "disallowed": [],
        "permission_mode": "acceptEdits",
        "writes": True,
        "launch_flags": [
            "--permission-mode",
            "acceptEdits",
            "--worktree",
            "<lane>",
            "--add-dir",
            "<scope>",
        ],
        "role": "a bounded implementer",
        "duties": [
            "Work only against an explicit written contract.",
            "Write only inside the declared scope below.",
            "Do not commit, push, deploy, or install dependencies.",
        ],
    },
}

#: Placeholders in `launch_flags` that a caller must substitute before the command
#: is runnable. Rendered documentation keeps them; `harness_session.py` fills them.
LAUNCH_PLACEHOLDERS = ("<lane>", "<scope>")

for _tier in CAPABILITY_TIERS.values():
    # Derived, never stored twice. The rendered launch line and the command the
    # session tooling actually builds must come from the same list, or a tier can
    # be documented one way and launched another.
    _tier["launch"] = " ".join(_tier["launch_flags"])
del _tier

DEFAULT_CAPABILITY = "reader"

# Permission modes that let an agent change files without asking. A tier whose
# `writes` flag is false must never render one of these.
EDIT_ACCEPTING_MODES = ("acceptEdits", "auto", "bypassPermissions")


def launch_command(capability: str) -> str:
    """The command that launches this tier, in the dispatch mode it can report from.

    Not cosmetic. `claude --bg` refuses `--print`, so a background session has no
    structured return channel and can only report by writing a bus envelope — and
    a read-only tier has no `Write` tool to write one with. Telling a `reader` to
    launch with `--bg` produces a session whose output is unreachable except as
    ANSI terminal capture. Measured in
    `.ai/reports/0001-session-substrate-smoke-test.md`.

    So the dispatch mode follows from the tier, not from the caller's preference:
    a writing tier can run detached and post its own envelope; a read-only tier
    runs in the foreground and the orchestrator reads its structured output.
    """
    tier = CAPABILITY_TIERS[capability]
    if tier["writes"]:
        return f"claude --bg {tier['launch']}"
    return f"claude -p {tier['launch']} --output-format json"


def capability_grant_errors(
    capability: str,
    writable: list[str],
    approved: bool,
    label: str,
) -> list[str]:
    """Check that a requested tier is one the caller may actually be granted.

    Lives here rather than in the renderer because the renderer is no longer the
    only thing that hands out a tier: an agent synthesized at work time goes
    through the same gate. Two copies of this rule would be two places for the
    writing tier to become reachable, and only one of them would be reviewed.

    Returns messages in the order they should be reported; the caller decides
    whether to fail on the first or collect them all.
    """
    errors: list[str] = []
    if capability not in CAPABILITY_TIERS:
        errors.append(f"{label}.capability must be one of {sorted(CAPABILITY_TIERS)}")
        return errors

    if capability == "implementer":
        # Compensating control 1: an implementer without a declared scope
        # would inherit the whole repository.
        if not writable:
            errors.append(
                f"{label} is an implementer and must declare a non-empty "
                "writable_paths scope"
            )
        # Compensating control 2: raising an agent to write authority is an
        # operator decision, never something a profile acquires silently.
        if not approved:
            errors.append(
                f"{label} is an implementer and requires approved_by_operator: true"
            )
    else:
        if writable:
            errors.append(
                f"{label}.writable_paths is only valid for an implementer; "
                f"{capability} agents never write"
            )
        if approved:
            errors.append(
                f"{label}.approved_by_operator is only meaningful for an implementer"
            )
    return errors

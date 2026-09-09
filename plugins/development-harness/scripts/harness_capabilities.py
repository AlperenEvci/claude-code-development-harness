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

# Flags no tier may launch with, whatever the table says. `--bare` skips hooks,
# plugin sync, auto-memory, and `CLAUDE.md` auto-discovery, so a session launched
# with it holds none of the contract the harness installed - and on subscription
# authentication it refuses to start at all. Measured on Claude Code 2.1.263; see
# `.ai/reports/0004-bare-flag-smoke-test.md`.
#
# The other two hosts have the same kind of flag, named in `codex --help` and in
# OpenCode's own documentation (reports 0012 and 0015): Codex's two bypasses
# remove the sandbox and the hook-trust requirement, and OpenCode's `--auto`
# auto-approves every permission that is not explicitly denied. They are listed
# here rather than in the launcher because the rule is the tier's, not the
# binary's: a tier that could hand itself more authority than the table grants
# is not a tier. The match is exact, so `--autocompact` is untouched by `--auto`.
FORBIDDEN_LAUNCH_FLAGS: tuple[str, ...] = (
    "--bare",
    "--dangerously-bypass-approvals-and-sandbox",
    "--dangerously-bypass-hook-trust",
    "--auto",
)

# The range `claude --autocompact` accepts, measured on 2.1.263 rather than read
# from the help line: `50000` and `2000000` are both refused at argument parsing
# with "It must be 'auto', or between 100k and 1M". See
# `.ai/reports/0006-compaction-smoke-test.md`.
#
# This lives here because two things need it and they must not disagree: the
# renderer narrows `context_policy.working_band.ceiling_tokens` to this range, and
# `harness_session.py` passes that ceiling to the flag. A profile the renderer
# accepted but the flag refuses is a harness that installs cleanly and then cannot
# open a session.
AUTOCOMPACT_MIN_TOKENS = 100_000
AUTOCOMPACT_MAX_TOKENS = 1_000_000


def autocompact_flag(ceiling_tokens: int) -> list[str]:
    """The launch flag that makes a declared ceiling the platform's business.

    Returns an empty list for a ceiling outside the accepted range instead of
    raising. The renderer refuses such a profile at render time, which is where
    the operator can still fix it; refusing again at launch would take a harness
    installed before that rule existed and leave it unable to start a session at
    all. Dropping the flag degrades to the behavior every release before this one
    had - the band as prose - which is worse than enforcement and better than a
    session that will not open.
    """
    if not isinstance(ceiling_tokens, int):
        return []
    # `True` needs no special case: it is 1, and 1 is already out of range.
    if ceiling_tokens < AUTOCOMPACT_MIN_TOKENS or ceiling_tokens > AUTOCOMPACT_MAX_TOKENS:
        return []
    return ["--autocompact", str(ceiling_tokens)]


#: The effort ladder `claude --effort` accepts, measured against CLI 2.1.263 in
#: `.ai/reports/0008-model-effort-and-agent-scoping.md`.
#:
#: This is deliberately NOT the Codex ladder. `render_harness.ALLOWED_REASONING`
#: is `{low, medium, high, xhigh}`; this one ends in `max`. The two are rendered
#: near each other in `CLAUDE.md`, where `codex_reasoning_line` already calls its
#: value "effort", so they are kept as separate constants with separate names to
#: stop one being validated against the other's set.
ALLOWED_EFFORT = ("low", "medium", "high", "xhigh", "max")

#: The model value that means "use whatever model the session is already running".
#: It is valid in agent frontmatter and *invalid* on the launcher, which rejects it
#: as `unrecognized_model` - on a zero exit code. `model_effort_flags` is the single
#: place that knows this, so the distinction cannot be forgotten at a call site.
MODEL_INHERIT = "inherit"


def model_effort_flags(model: str | None, effort: str | None) -> list[str]:
    """Return the `--model` / `--effort` flags a tier contributes, or neither.

    Shaped like `autocompact_flag`: a caller appends the result unconditionally
    and gets nothing when there is nothing to say.

    `inherit` yields no `--model`. Passing it through would fail the session at the
    API with `unrecognized_model`, and it would fail only for the implementer tier,
    whose default it is - the tier launched least often and debugged most expensively.
    An effort outside `ALLOWED_EFFORT` is dropped here as a last resort; the real
    gate is `validate_harness.py`, because the CLI only *warns* on an unknown value
    and then runs at its default, so nothing downstream can tell it was discarded.
    """
    flags: list[str] = []
    resolved_model = str(model or "").strip()
    if resolved_model and resolved_model != MODEL_INHERIT:
        flags += ["--model", resolved_model]
    resolved_effort = str(effort or "").strip().lower()
    if resolved_effort in ALLOWED_EFFORT:
        flags += ["--effort", resolved_effort]
    return flags


CAPABILITY_TIERS: dict[str, dict[str, Any]] = {
    "reader": {
        "tools": ["Read", "Grep", "Glob"],
        "disallowed": ["Write", "Edit", "Bash"],
        "permission_mode": "plan",
        "writes": False,
        "launch_flags": ["--permission-mode", "plan", "--tools", "Read,Grep,Glob"],
        "model": "sonnet",
        "effort": "medium",
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
        "model": "sonnet",
        "effort": "medium",
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
        "model": "inherit",
        "effort": "high",
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


def launch_command(
    capability: str,
    model: str | None = None,
    effort: str | None = None,
) -> str:
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

    `model` and `effort` default to the tier's, and a caller passes them only to
    reflect a profile that overrode one. They are arguments rather than entries in
    `launch_flags` because `launch_flags` is a constant and these two are the only
    part of a tier an operator may configure; putting a configurable value in the
    shared table would mean the table no longer describes every package that uses
    it. What the table still guarantees is that the documented command and the
    command `harness_session.py` builds are assembled from one function.
    """
    tier = CAPABILITY_TIERS[capability]
    tuning = " ".join(
        model_effort_flags(
            tier["model"] if model is None else model,
            tier["effort"] if effort is None else effort,
        )
    )
    tuning = f" {tuning}" if tuning else ""
    if tier["writes"]:
        return f"claude --bg {tier['launch']}{tuning}"
    return f"claude -p {tier['launch']}{tuning} --output-format json"


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


# --- The Codex sandbox floor -----------------------------------------------
#
# Here for the reason the tier table is here: the renderer writes this floor,
# the validator checks the rendered file against the profile, and the checker
# reads the installed one back. Three copies of the mapping would be three
# places for authority and its enforcement to drift apart.
#
# Measured on Codex CLI 0.153.4, `.ai/reports/0015-codex-enforcement-surface.md`:
# a project `.codex/config.toml` sets the session sandbox with no command-line
# flag and no trust prompt, and the sandbox is enforced by the operating system.
# It is a default rather than a ceiling - `codex exec -s workspace-write`
# overrides it - and the same file can widen a sandbox as easily as narrow one,
# which is why the checker reads it back instead of trusting what was rendered.

#: Autonomy to sandbox mode. Codex has three modes and no enforceable "ask": a
#: project config asking for `approval_policy = "on-request"` still reports
#: `approval: never` under `codex exec`, so a policy meaning "ask first" rounds
#: down to the mode that cannot write rather than up to the one that can.
CODEX_AUTONOMY_SANDBOX: dict[str, str] = {
    "read-only": "read-only",
    "approval-required": "read-only",
    "repository-write-with-approval": "workspace-write",
    "isolated-auto": "workspace-write",
}

#: Network policy to the one network switch the sandbox honors. Measured as a
#: pair: the same request to the same host returned "cannot reach the remote
#: server" with `false` and `200` with `true`.
CODEX_NETWORK_ACCESS: dict[str, bool] = {
    "deny-by-default": False,
    "ask-before-network": False,
    "approved-for-scoped-tasks": True,
}

#: How much authority each mode carries, so "wider than the profile allows" is
#: a comparison rather than a judgement. `danger-full-access` is never rendered
#: by anything in this repository; it is in the table only so an installed file
#: claiming it can be recognized and refused.
CODEX_SANDBOX_RANK: dict[str, int] = {
    "read-only": 0,
    "workspace-write": 1,
    "danger-full-access": 2,
}


def codex_sandbox_floor(profile: dict[str, Any]) -> dict[str, Any]:
    """The sandbox a profile's declared policy implies.

    Two keys at most, because two are all a project file was measured to
    enforce. `network_access` only applies inside the workspace-write sandbox,
    so a read-only floor omits it rather than stating something inapplicable.
    """
    mode = CODEX_AUTONOMY_SANDBOX.get(str(profile.get("autonomy", "")))
    if mode is None:
        return {}
    floor: dict[str, Any] = {"sandbox_mode": mode}
    if mode == "workspace-write":
        network = CODEX_NETWORK_ACCESS.get(str(profile.get("network_access", "")))
        if network is not None:
            floor["network_access"] = network
    return floor


def read_codex_config(text: str) -> dict[str, Any]:
    """The three things anything here needs to know about a `.codex/config.toml`.

    Not a TOML parser, and not pretending to be one: `tomllib` is 3.11 and this
    repository supports 3.10. It reads the top-level `sandbox_mode`, the
    `network_access` under `[sandbox_workspace_write]`, and the names of any
    `[agents.<name>]` role tables - which is exactly what the floor check and
    the widening check need, and nothing else. A key it cannot read is reported
    as absent, so an unreadable file fails the comparison rather than passing it.
    """
    result: dict[str, Any] = {"sandbox_mode": None, "network_access": None, "roles": []}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.startswith("agents."):
                result["roles"].append(section[len("agents."):].strip().strip('"'))
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if not section and key == "sandbox_mode":
            result["sandbox_mode"] = value
        elif section == "sandbox_workspace_write" and key == "network_access":
            result["network_access"] = value == "true"
    return result

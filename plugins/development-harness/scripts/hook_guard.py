#!/usr/bin/env python3
"""`PreToolUse` guard: deny what the contract already forbids in prose.

The generated `AGENTS.md` says not to open secret-bearing files and not to run
destructive git. Both are requests. A `PreToolUse` hook is the enforcement,
because it runs before the permission check in every mode, including
`bypassPermissions`, and a `deny` cannot be loosened by a mode.

Three deliberate limits, each of which is a real weakness rather than a
rhetorical one:

**It fails open.** A crash exits 1, which Claude Code reports as a non-blocking
hook error, and the tool call proceeds. Failing closed would let a defect in this
file lock an operator out of their own repository. The fallback is the prose rule
that was there before this hook existed, so a crash returns the harness to its
previous state loudly rather than to a worse one silently.

**It reads a command, not a shell.** A `Bash` command is matched with patterns.
Anything genuinely determined to get past that will: `eval`, a wrapper script, a
here-doc. This is defense in depth over the permission system, never a sandbox.

**It denies; it never allows.** No path through this file emits an allow
decision. A guard that could grant would be a way to widen authority from inside
the repository, which is exactly what the untrusted-text rule forbids.

Escape hatch: set `HARNESS_HOOKS_DISABLE=1` to make every harness hook exit 0
without reading its input.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

EXIT_ALLOW = 0
# `PreToolUse` treats exit 2 as a block and shows stderr to the model.
EXIT_DENY = 2

DISABLE_ENV = "HARNESS_HOOKS_DISABLE"

# Kept in step with `inspect_project.SECRET_FILENAMES` by a test rather than by
# an import: the inspector is a plugin script and is never installed into a
# target repository, so this file cannot import it and must not pretend to.
SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    ".envrc",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".htpasswd",
    "credentials",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
    "settings.local.json",
}

SECRET_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".asc")

# Directory fragments whose contents are credentials whatever the file is called.
SECRET_DIR_FRAGMENTS = ("/.ssh/", "/.aws/", "/.gnupg/", "/.docker/config")

READ_TOOLS = {"Read", "NotebookRead"}
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}

# Destructive git, denied under every commit policy. Each of these discards work
# that the operator did not ask an agent to discard.
ALWAYS_DENIED_GIT = (
    (r"\bgit\s+reset\s+(--\S+\s+)*--hard\b", "git reset --hard discards local work"),
    (r"\bgit\s+clean\s+(-\S*f|--force)", "git clean deletes untracked files"),
    (r"\bgit\s+checkout\s+--\s", "git checkout -- discards uncommitted changes"),
    (r"\bgit\s+push\s+(--force|-f)\b", "a force push rewrites published history"),
    (r"\bgit\s+push\s+.*--force", "a force push rewrites published history"),
    (r"\bgit\s+branch\s+(-D|--delete\s+--force)", "a forced branch delete loses commits"),
    (r"\bgit\s+filter-branch\b", "filter-branch rewrites every commit"),
    (r"\bgit\s+reflog\s+(expire|delete)", "expiring the reflog removes the last safety net"),
)

# Denied unless the profile's commit policy allows the agent to commit.
COMMIT_GIT = (
    (r"\bgit\s+commit\b", "git commit"),
    (r"\bgit\s+merge\b", "git merge"),
    (r"\bgit\s+rebase\b", "git rebase"),
)

# Denied under every policy: publishing is outward-facing and is the operator's.
PUSH_GIT = ((r"\bgit\s+push\b", "git push"),)

RM_PATTERN = re.compile(r"\brm\s+(-\S+\s+)*-\S*[rR]\S*f|\brm\s+(-\S+\s+)*-\S*f\S*[rR]")


def disabled() -> bool:
    return os.environ.get(DISABLE_ENV, "") == "1"


def deny(reason: str) -> None:
    """Refuse the call and tell the model why in one line it can act on."""
    print(f"harness guard: {reason}", file=sys.stderr)
    raise SystemExit(EXIT_DENY)


def load_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def commit_policy(cwd: Path) -> str:
    """Read the installed profile, the way the checkpoint script does.

    The policy the operator chose at setup is the one the guard enforces. A
    missing or unreadable profile falls back to the stricter answer, because a
    guard that guesses should guess toward refusing.
    """
    profile = cwd / ".ai" / "harness" / "project-profile.json"
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "no-commit"
    value = data.get("agent_commit_policy")
    return str(value) if isinstance(value, str) else "no-commit"


def looks_secret(raw_path: str) -> str | None:
    """Return the reason this path is secret-bearing, or None."""
    if not raw_path:
        return None
    text = str(raw_path).replace("\\", "/")
    name = text.rsplit("/", 1)[-1]

    if name in SECRET_FILENAMES:
        return f"{name} is a secret-bearing file"
    if name.startswith(".env"):
        return f"{name} is an environment file"
    for suffix in SECRET_SUFFIXES:
        if name.endswith(suffix):
            return f"{name} looks like a key or certificate"
    lowered = "/" + text.lower().lstrip("/")
    for fragment in SECRET_DIR_FRAGMENTS:
        if fragment in lowered:
            return f"{text} is inside a credential directory"
    return None


def guard_file_tool(tool: str, tool_input: dict) -> None:
    for key in ("file_path", "path", "notebook_path"):
        found = looks_secret(str(tool_input.get(key, "")))
        if found:
            verb = "write to" if tool in WRITE_TOOLS else "read"
            deny(
                f"refusing to {verb} it: {found}. Report such files by name only. "
                f"Set {DISABLE_ENV}=1 if the operator has authorized this."
            )


def guard_bash(command: str, policy: str) -> None:
    if not command:
        return
    # A newline-joined command is still one command line to the shell.
    flat = " ".join(command.split())

    for pattern, reason in ALWAYS_DENIED_GIT:
        if re.search(pattern, flat):
            deny(f"refusing this command: {reason}")

    for pattern, label in PUSH_GIT:
        if re.search(pattern, flat):
            deny(
                f"refusing {label}: publishing is an operator action, not an "
                "agent one, whatever the commit policy says"
            )

    if policy != "commit-locally":
        for pattern, label in COMMIT_GIT:
            if re.search(pattern, flat):
                deny(
                    f"refusing {label}: the agent commit policy is {policy}. "
                    "Leave the change in the working tree and say what you did."
                )

    if RM_PATTERN.search(flat):
        for target in (" /", " ~", " .git", " ..", " $HOME", " /*"):
            if f"{target} " in f"{flat} " or flat.rstrip().endswith(target):
                deny(
                    "refusing a recursive force delete of "
                    f"{target.strip()}: name the paths explicitly instead"
                )

    for token in ("--dangerously-skip-permissions", "--permission-mode bypassPermissions"):
        if token in flat:
            deny(
                f"refusing a command carrying {token}: a session may not widen "
                "its own authority"
            )


def main() -> int:
    if disabled():
        return EXIT_ALLOW

    payload = load_payload()
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool in READ_TOOLS or tool in WRITE_TOOLS:
        guard_file_tool(tool, tool_input)
        return EXIT_ALLOW

    if tool == "Bash":
        cwd = Path(str(payload.get("cwd") or ".")).resolve()
        guard_bash(str(tool_input.get("command", "")), commit_policy(cwd))

    return EXIT_ALLOW


if __name__ == "__main__":
    raise SystemExit(main())

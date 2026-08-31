#!/usr/bin/env python3
"""Check an installed development harness for structural and safety issues."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_capabilities import (  # noqa: E402  (sibling module, resolved above)
    CAPABILITY_TIERS,
    EDIT_ACCEPTING_MODES,
)

PLACEHOLDER = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FENCED_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)

BASE_REQUIRED = [
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/skills/harness-orchestration/SKILL.md",
    ".ai/README.md",
    ".ai/backlog.md",
    ".ai/templates/report.md",
    ".ai/templates/decision.md",
    ".ai/templates/spec.md",
    ".ai/harness/project-profile.json",
    "docs/ai-harness/README.md",
]

STANDARD_REQUIRED = [
    ".claude/agents/harness-codebase-researcher.md",
    ".claude/agents/harness-code-reviewer.md",
    # The session tooling is what makes a capability tier enforceable at launch
    # and what stops a background agent being orphaned. An installed harness
    # missing it still has the agents but no way to run or retire them safely.
    "scripts/ai-harness/harness_capabilities.py",
    "scripts/ai-harness/harness_bus.py",
    "scripts/ai-harness/harness_session.py",
    "scripts/ai-harness/harness_agentgen.py",
    # 1.3 and 1.4 added two more, and this list did not follow them. An
    # installed harness missing these has a context band and a definition of
    # done that are prose again, which is exactly what those releases fixed.
    "scripts/ai-harness/harness_checkpoint.py",
    "scripts/ai-harness/harness_progress.py",
    # 1.8. Without it the recorded state is present but unreadable as a whole.
    "scripts/ai-harness/harness_report.py",
    ".ai/progress.json",
]

FLEET_REQUIRED = [
    ".claude/skills/harness-codex-fleet/SKILL.md",
    ".ai/templates/lane-brief.md",
    ".ai/templates/ledger.md",
    "scripts/ai-harness/create-lane-worktree.sh",
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def frontmatter_list(text: str, key: str) -> list[str] | None:
    """Return a YAML block-sequence frontmatter value, or None when absent."""
    match = re.search(
        rf"^{re.escape(key)}:[ \t]*\n((?:[ \t]*-[ \t]*\S+[ \t]*\n)+)",
        text,
        re.MULTILINE,
    )
    if match is None:
        return None
    return [line.strip().lstrip("-").strip() for line in match.group(1).splitlines()]


def check_agent_authority(
    rel: str, text: str, errors: list[str], warnings: list[str]
) -> str | None:
    """Read an installed agent's authority off its own frontmatter.

    The installed harness is the copy that actually runs, and it can be edited
    after installation, so the tier a file names is checked against what the
    file actually grants rather than against the profile that produced it. An
    agent declaring a read-only tier while carrying edit-accepting authority is
    an escalation regardless of how it got there, and so an error.

    This mirrors `validate_harness.check_declared_tier` deliberately. The
    package validator is the last gate before installation; this is the only
    gate after it, and a boundary enforced on one side of the copy and not the
    other is not a boundary. Returns the capability it found, or None.
    """
    match = re.search(r"^capability:\s*(\S+)\s*$", text, re.MULTILINE)
    if match is None:
        warnings.append(f"agent does not declare a capability tier: {rel}")
        return None

    capability = match.group(1).strip().strip("\"'")
    tier = CAPABILITY_TIERS.get(capability)
    if tier is None:
        errors.append(f"agent declares unknown capability {capability!r}: {rel}")
        return None

    # The whole list, not a prefix: a substring match would accept an agent that
    # kept its tier's tools and appended Write to them.
    if frontmatter_list(text, "tools") != tier["tools"]:
        errors.append(f"agent tools do not match its {capability} tier: {rel}")

    if (frontmatter_list(text, "disallowedTools") or []) != tier["disallowed"]:
        errors.append(
            f"agent does not deny the tools its {capability} tier forbids: {rel}"
        )

    if f"permissionMode: {tier['permission_mode']}" not in text:
        errors.append(
            f"agent permission mode does not match its {capability} tier: {rel}"
        )

    if not tier["writes"]:
        for mode in EDIT_ACCEPTING_MODES:
            if re.search(rf"^permissionMode:\s*{mode}\s*$", text, re.MULTILINE):
                errors.append(
                    f"{capability} agent carries permission mode {mode}: {rel}"
                )
    return capability


def frontmatter_keys(text: str) -> set[str]:
    match = FRONTMATTER.search(text)
    if not match:
        return set()
    keys = set()
    for line in match.group(1).splitlines():
        if line and not line.startswith((" ", "\t", "-")) and ":" in line:
            keys.add(line.split(":", 1)[0].strip())
    return keys




def executable_code_blocks(text: str) -> list[str]:
    """Return shell-like fenced blocks, excluding explanatory prose."""

    blocks: list[str] = []
    for match in FENCED_BLOCK.finditer(text):
        language = match.group(1).strip().lower()
        if language in {"", "bash", "sh", "shell", "zsh"}:
            blocks.append(match.group(2))
    return blocks


def slugify(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "component"
    return text if text.startswith("harness-") else f"harness-{text}"


def dynamic_component_paths(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    mappings = (
        ("scoped_rules", ".claude/rules", ".md"),
        ("additional_skills", ".claude/skills", "/SKILL.md"),
        ("additional_agents", ".claude/agents", ".md"),
    )
    for key, base, suffix in mappings:
        items = profile.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = slugify(item.get("name"))
            result[f"{base}/{name}{suffix}"] = {"kind": key, "profile": item}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"error: root is not a directory: {root}")

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    profile_path = root / ".ai/harness/project-profile.json"
    profile: dict[str, Any] = {}
    if profile_path.exists():
        try:
            loaded = json.loads(profile_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                profile = loaded
            else:
                errors.append(".ai/harness/project-profile.json is not a JSON object")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid project profile: {exc}")
    elif not args.allow_missing:
        errors.append("missing .ai/harness/project-profile.json")

    tier = str(profile.get("harness_tier", "standard")).lower()
    mode = str(profile.get("harness_mode", "adopt")).lower()
    delegate = str(profile.get("implementation_delegate", "codex-cli")).lower()
    greenfield = profile.get("greenfield_context")
    dynamic = dynamic_component_paths(profile)
    required = list(BASE_REQUIRED)
    if mode == "create":
        required.extend([
            ".ai/project/brief.md",
            ".ai/project/architecture.md",
            ".ai/project/roadmap.md",
            ".ai/project/open-questions.md",
        ])
        if isinstance(greenfield, dict) and greenfield.get("create_root_readme", True):
            required.append("README.md")
        if isinstance(greenfield, dict) and greenfield.get("setup_depth") == "ready-to-build":
            required.append(".ai/specs/current-task.md")
        if tier == "fleet":
            errors.append("greenfield create mode may not start at Fleet tier")
    if delegate != "claude-only":
        required.append(".claude/skills/harness-codex-delegate/SKILL.md")
    if tier in {"standard", "fleet"}:
        required.extend(STANDARD_REQUIRED)
    if tier == "fleet":
        required.extend(FLEET_REQUIRED)
        if delegate != "codex-cli":
            errors.append("fleet harness requires implementation_delegate=codex-cli")
    required.extend(dynamic)

    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        target = warnings if args.allow_missing else errors
        target.extend(f"missing required file: {rel}" for rel in missing)

    if tier in {"standard", "fleet"}:
        claude_text = read_text(root / "CLAUDE.md")
        if claude_text and "## Agent sessions" not in claude_text:
            warnings.append(
                "CLAUDE.md has no `## Agent sessions` section; this harness "
                "predates session support, re-render to add it"
            )
        elif claude_text and "harness_session.py sweep" not in claude_text:
            warnings.append(
                "CLAUDE.md documents agent sessions but not the teardown sweep; "
                "background agents can be left running"
            )

    claude_path = root / "CLAUDE.md"
    agents_path = root / "AGENTS.md"
    claude_text = read_text(claude_path)
    agents_text = read_text(agents_path)

    if claude_path.exists() and "@AGENTS.md" not in claude_text:
        warnings.append("CLAUDE.md does not import @AGENTS.md; shared rules may drift")
    if claude_text and claude_text.count("\n") + 1 > 220:
        warnings.append("CLAUDE.md exceeds 220 lines; move procedures to skills or scoped rules")
    if agents_text and agents_text.count("\n") + 1 > 220:
        warnings.append("AGENTS.md exceeds 220 lines; keep the shared contract concise")

    inspect_paths = set(required)
    for base in (root / ".claude/skills", root / ".claude/agents", root / ".claude/rules"):
        if base.exists():
            # POSIX separators: the prefix matches below are written with '/'.
            inspect_paths.update(
                path.relative_to(root).as_posix() for path in base.rglob("*.md")
            )

    for rel in sorted(inspect_paths):
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        # Reset per file: the component check below reads it, and a value left
        # over from the previous path would be answering about another file.
        declared: str | None = None
        if PLACEHOLDER.search(text):
            errors.append(f"unresolved template placeholder: {rel}")
        if rel.endswith("SKILL.md"):
            keys = frontmatter_keys(text)
            if "description" not in keys:
                warnings.append(f"skill missing description frontmatter: {rel}")
        if rel.startswith(".claude/agents/"):
            keys = frontmatter_keys(text)
            for key in ("name", "description"):
                if key not in keys:
                    errors.append(f"agent missing {key} frontmatter: {rel}")
            declared = check_agent_authority(rel, text, errors, warnings)
        if rel.startswith(".claude/rules/") and rel in dynamic:
            if "paths" not in frontmatter_keys(text):
                errors.append(f"generated scoped rule missing paths frontmatter: {rel}")

        component = dynamic.get(rel)
        if component and component["kind"] == "additional_skills":
            keys = frontmatter_keys(text)
            if "allowed-tools" in keys:
                errors.append(f"generated project skill pre-approves tools: {rel}")
            if component["profile"].get("manual_only", True) and "disable-model-invocation" not in keys:
                errors.append(f"manual generated project skill is model-invocable: {rel}")
        if component and component["kind"] == "additional_agents":
            # What the tier grants is checked above, for every agent file in the
            # project. What is specific to a generated one is that it must name
            # a tier at all: the renderer always writes one, so a file that has
            # lost it has been edited, and an unnamed tier is unenforceable.
            #
            # This replaced a literal `Read/Grep/Glob` fragment match, which was
            # the pre-1.0 rule that every domain agent is read-only. Capability
            # tiers superseded that in 1.0, and a correctly generated verifier
            # or implementer had been failing here ever since.
            if declared is None:
                errors.append(
                    f"generated domain agent declares no capability tier: {rel}"
                )

    codex_path = root / ".claude/skills/harness-codex-delegate/SKILL.md"
    codex_skill = read_text(codex_path)
    if delegate == "claude-only":
        if codex_path.exists():
            errors.append("claude-only profile should not install a Codex delegate skill")
        info.append("Claude-only implementation transport configured")
    elif codex_skill:
        forbidden = [
            "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-skip-permissions",
            "--skip-git-repo-check",
            "danger-full-access",
        ]
        executable_text = "\n".join(executable_code_blocks(codex_skill))
        for token in forbidden:
            if token in executable_text:
                errors.append(f"unsafe/default-bypass token in executable Codex command: {token}")
        if delegate == "codex-plugin":
            if "codex:codex-rescue" not in codex_skill:
                errors.append("official Codex plugin transport is missing codex:codex-rescue")
            else:
                info.append("Official Codex Claude Code plugin transport configured; verify it in /agents")
        elif delegate == "codex-cli":
            if shutil.which("codex") is None:
                warnings.append("Codex CLI is not on PATH; direct CLI delegation cannot execute yet")
            else:
                info.append("Codex CLI found on PATH")

    if (root / ".claude/settings.json").exists():
        text = read_text(root / ".claude/settings.json")
        if "bypassPermissions" in text or "dangerously" in text:
            warnings.append("project Claude settings mention bypass/dangerous permissions; review manually")

    if mode == "create":
        info.append("Greenfield project context is installed under .ai/project")
        if isinstance(greenfield, dict):
            info.append(
                "Greenfield setup depth: "
                + str(greenfield.get("setup_depth", "context-only"))
            )

    result = {
        "root": str(root),
        "mode": mode,
        "tier": tier,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "status": "fail" if errors else "pass-with-warnings" if warnings else "pass",
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Harness check: {result['status']} (mode: {mode}, tier: {tier})")
        for item in errors:
            print(f"ERROR: {item}")
        for item in warnings:
            print(f"WARNING: {item}")
        for item in info:
            print(f"INFO: {item}")

    if errors and not args.allow_missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

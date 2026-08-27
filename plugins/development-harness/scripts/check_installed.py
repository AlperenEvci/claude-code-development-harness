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

PLACEHOLDER = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

BASE_REQUIRED = [
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/skills/harness-orchestration/SKILL.md",
    ".claude/skills/harness-codex-delegate/SKILL.md",
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


def frontmatter_keys(text: str) -> set[str]:
    match = FRONTMATTER.search(text)
    if not match:
        return set()
    keys = set()
    for line in match.group(1).splitlines():
        if line and not line.startswith((" ", "\t", "-")) and ":" in line:
            keys.add(line.split(":", 1)[0].strip())
    return keys




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
    dynamic = dynamic_component_paths(profile)
    required = list(BASE_REQUIRED)
    if tier in {"standard", "fleet"}:
        required.extend(STANDARD_REQUIRED)
    if tier == "fleet":
        required.extend(FLEET_REQUIRED)
    required.extend(dynamic)

    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        target = warnings if args.allow_missing else errors
        target.extend(f"missing required file: {rel}" for rel in missing)

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
            inspect_paths.update(str(path.relative_to(root)) for path in base.rglob("*.md"))

    for rel in sorted(inspect_paths):
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
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
            required_fragments = (
                "tools:\n  - Read\n  - Grep\n  - Glob",
                "disallowedTools:\n  - Write\n  - Edit\n  - Bash",
                "permissionMode: plan",
            )
            for fragment in required_fragments:
                if fragment not in text:
                    errors.append(f"generated domain agent is not read-only: {rel}")
                    break

    codex_skill = read_text(root / ".claude/skills/harness-codex-delegate/SKILL.md")
    if codex_skill:
        forbidden = [
            "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-skip-permissions",
            "--skip-git-repo-check",
            "danger-full-access",
        ]
        for token in forbidden:
            if token in codex_skill:
                errors.append(f"unsafe/default-bypass token in Codex delegate skill: {token}")
        if shutil.which("codex") is None:
            warnings.append("Codex CLI is not on PATH; delegation skill cannot execute yet")
        else:
            info.append("Codex CLI found on PATH")

    if (root / ".claude/settings.json").exists():
        text = read_text(root / ".claude/settings.json")
        if "bypassPermissions" in text or "dangerously" in text:
            warnings.append("project Claude settings mention bypass/dangerous permissions; review manually")

    result = {
        "root": str(root),
        "tier": tier,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "status": "fail" if errors else "pass-with-warnings" if warnings else "pass",
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Harness check: {result['status']} (tier: {tier})")
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

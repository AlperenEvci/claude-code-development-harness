#!/usr/bin/env python3
"""Inspect a repository without reading secret values or modifying the project.

The output is evidence for the Development Harness setup/audit skills. It is
heuristic by design: detected commands are candidates until verified by the
repository or the user.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "dist",
    "build",
    "coverage",
    ".coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    "target",
    ".turbo",
    ".cache",
}

BENIGN_GREENFIELD_FILES = {".DS_Store", "Thumbs.db", ".gitkeep"}

SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}

LANG_BY_EXT = {
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".py": "Python",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C/C++",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".scala": "Scala",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".sol": "Solidity",
    ".sql": "SQL",
    ".sh": "Shell",
}

FRAMEWORK_DEPS = {
    "next": "Next.js",
    "react": "React",
    "react-native": "React Native",
    "expo": "Expo",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit",
    "astro": "Astro",
    "vite": "Vite",
    "express": "Express",
    "@nestjs/core": "NestJS",
    "fastify": "Fastify",
    "remix": "Remix",
    "@remix-run/react": "Remix",
    "electron": "Electron",
    "tauri": "Tauri",
    "jest": "Jest",
    "vitest": "Vitest",
    "@playwright/test": "Playwright",
    "cypress": "Cypress",
    "prisma": "Prisma",
    "drizzle-orm": "Drizzle ORM",
    "@supabase/supabase-js": "Supabase",
}

HARNESS_PATHS = [
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".claude/CLAUDE.md",
    ".claude/rules",
    ".claude/skills",
    ".claude/agents",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".agents/skills",
    ".ai",
    "docs/ai-harness",
]

MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "uv.lock",
    "go.mod",
    "Cargo.toml",
    "composer.json",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Package.swift",
    "pubspec.yaml",
    "mix.exs",
}


def run(command: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=12,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def safe_json(path: Path, max_bytes: int = 1_000_000) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def safe_text(path: Path, max_bytes: int = 250_000) -> str:
    if path.name in SECRET_FILENAMES or path.name.startswith(".env"):
        return ""
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def file_meta(path: Path, root: Path) -> dict[str, Any]:
    """Return metadata only. Do not read the file body."""
    kind = "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file"
    item: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "kind": kind,
    }
    try:
        if path.is_symlink():
            item["target_not_followed"] = True
        elif path.is_file():
            item["bytes"] = path.stat().st_size
        elif path.is_dir():
            item["entries"] = sum(1 for _ in path.iterdir())
    except OSError:
        pass
    return item


def iter_project_files(root: Path, limit: int = 12_000):
    seen = 0
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        current_path = Path(current)
        for filename in sorted(filenames):
            path = current_path / filename
            # Metadata is safe to inspect, but downstream readers must never follow
            # repository-controlled symlinks outside the project.
            yield path
            seen += 1
            if seen >= limit:
                return


def detect_package_manager(root: Path, package: dict[str, Any] | None) -> str:
    if (root / "pnpm-lock.yaml").exists() or (root / "pnpm-workspace.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    if (root / "package-lock.json").exists() or (root / "npm-shrinkwrap.json").exists():
        return "npm"
    if package:
        value = str(package.get("packageManager", ""))
        if value:
            return value.split("@", 1)[0]
        return "npm"
    if (root / "uv.lock").exists():
        return "uv"
    if (root / "poetry.lock").exists():
        return "poetry"
    if (root / "Pipfile.lock").exists():
        return "pipenv"
    return "unknown"


def script_command(pm: str, script: str) -> str:
    if pm == "npm":
        return "npm test" if script == "test" else f"npm run {script}"
    if pm in {"pnpm", "yarn", "bun"}:
        return f"{pm} {script}"
    return f"<package-manager> run {script}"


def detect_commands(root: Path, package: dict[str, Any] | None, pm: str) -> dict[str, Any]:
    result: dict[str, Any] = {"source": None, "candidates": {}}
    candidates: dict[str, str] = result["candidates"]

    if package:
        scripts = package.get("scripts", {})
        if isinstance(scripts, dict):
            result["source"] = "package.json scripts"
            if pm == "npm":
                candidates["install"] = "npm ci" if (root / "package-lock.json").exists() else "npm install"
            elif pm in {"pnpm", "yarn", "bun"}:
                candidates["install"] = f"{pm} install"
            for label, names in {
                "dev": ["dev", "start"],
                "test": ["test"],
                "typecheck": ["typecheck", "type-check", "check:types", "tsc"],
                "lint": ["lint"],
                "build": ["build"],
            }.items():
                for name in names:
                    if name in scripts:
                        candidates[label] = script_command(pm, name)
                        break
            gate_parts = [
                candidates[key]
                for key in ("lint", "typecheck", "test", "build")
                if key in candidates
            ]
            if gate_parts:
                candidates["full_gate"] = " && ".join(gate_parts)

    if not candidates and (root / "Makefile").exists():
        text = safe_text(root / "Makefile")
        targets = []
        for line in text.splitlines():
            if line and not line.startswith(("\t", " ", ".")) and ":" in line:
                target = line.split(":", 1)[0].strip()
                if target and target.replace("-", "").replace("_", "").isalnum():
                    targets.append(target)
        result["source"] = "Makefile targets"
        result["make_targets"] = sorted(set(targets))[:40]

    return result


def detect_python_frameworks(root: Path) -> list[str]:
    frameworks: set[str] = set()
    for name in ("pyproject.toml", "requirements.txt", "Pipfile"):
        path = root / name
        if not path.exists():
            continue
        text = safe_text(path).lower()
        for needle, label in {
            "django": "Django",
            "fastapi": "FastAPI",
            "flask": "Flask",
            "pytest": "pytest",
            "sqlalchemy": "SQLAlchemy",
            "pydantic": "Pydantic",
        }.items():
            if needle in text:
                frameworks.add(label)
    return sorted(frameworks)


def detect_repo_shape(root: Path, package: dict[str, Any] | None) -> str:
    if (root / "pnpm-workspace.yaml").exists() or (root / "lerna.json").exists():
        return "monorepo"
    if (root / "turbo.json").exists() or (root / "nx.json").exists():
        return "monorepo"
    if package and package.get("workspaces"):
        return "monorepo"
    for dirname in ("apps", "packages", "services"):
        base = root / dirname
        if base.is_dir():
            manifest_count = 0
            for child in base.iterdir():
                if child.is_dir() and any((child / name).exists() for name in MANIFEST_NAMES):
                    manifest_count += 1
            if manifest_count >= 2:
                return "monorepo"
    if any((root / name).exists() for name in MANIFEST_NAMES):
        return "single-project"
    return "unknown"


def classify_project_state(
    top_level: list[dict[str, str]],
    manifests: list[str],
    language_counts: Counter[str],
    existing_harness: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify whether setup is entering a blank, minimal, or existing project.

    A README, a short product brief, or editor metadata should not force an
    empty-folder user into the existing-repository interview. The result is a
    recommendation only; an explicit user statement remains authoritative.
    """

    meaningful = [
        item
        for item in top_level
        if item.get("name") not in BENIGN_GREENFIELD_FILES
    ]
    names = {str(item.get("name", "")).lower() for item in meaningful}
    has_manifest = bool(manifests)
    source_file_count = sum(language_counts.values())
    has_source = source_file_count > 0
    has_harness = bool(existing_harness)

    planning_only_names = {
        "readme",
        "readme.md",
        "project.md",
        "brief.md",
        "idea.md",
        "notes.md",
        "docs",
    }
    planning_only = bool(meaningful) and names.issubset(planning_only_names)

    if not meaningful:
        classification = "empty"
        reason = "No meaningful project files were detected."
    elif not has_manifest and not has_source and not has_harness and planning_only:
        classification = "minimal-planning"
        reason = "Only lightweight planning or README material was detected."
    elif has_harness and not has_manifest and not has_source:
        classification = "harness-only"
        reason = "Harness files exist, but no meaningful application code or manifest was detected."
    else:
        classification = "existing"
        reason = "Application code, manifests, or established project structure was detected."

    greenfield_candidate = classification in {"empty", "minimal-planning"}
    suggested_mode = (
        "create"
        if greenfield_candidate
        else "upgrade"
        if has_harness
        else "adopt"
    )

    return {
        "classification": classification,
        "greenfield_candidate": greenfield_candidate,
        "suggested_harness_mode": suggested_mode,
        "reason": reason,
        "meaningful_top_level_count": len(meaningful),
        "meaningful_top_level_names": sorted(
            str(item.get("name", "")) for item in meaningful
        )[:40],
        "manifest_count": len(manifests),
        "source_file_count": source_file_count,
        "existing_harness_detected": has_harness,
    }


def detect_tools(root: Path) -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for name in ("claude", "codex", "git", "python3"):
        path = shutil.which(name)
        item: dict[str, Any] = {"available": bool(path), "path": path}
        if path:
            rc, stdout, stderr = run([name, "--version"], root)
            version = stdout or stderr
            if rc == 0 and version:
                item["version"] = version.splitlines()[0][:200]
        tools[name] = item
    return tools

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()

    requested_root = args.root.expanduser().resolve()
    if not requested_root.is_dir():
        raise SystemExit(f"error: root is not a directory: {requested_root}")

    rc, git_top, _ = run(["git", "rev-parse", "--show-toplevel"], requested_root)
    git_root = Path(git_top).resolve() if rc == 0 and git_top else None

    package = safe_json(requested_root / "package.json") if (requested_root / "package.json").exists() else None
    pm = detect_package_manager(requested_root, package)

    language_counts: Counter[str] = Counter()
    manifests: list[str] = []
    secret_files: list[str] = []
    test_markers: list[str] = []
    scanned_files = 0

    for path in iter_project_files(requested_root):
        scanned_files += 1
        rel = path.relative_to(requested_root).as_posix()
        if path.name in MANIFEST_NAMES and len(manifests) < 100:
            manifests.append(rel)
        if path.name in SECRET_FILENAMES or path.name.startswith(".env"):
            if len(secret_files) < 40:
                secret_files.append(rel)
            continue
        lang = LANG_BY_EXT.get(path.suffix.lower())
        if lang:
            language_counts[lang] += 1
        lower = rel.lower()
        if any(marker in lower for marker in ("test", "spec", "__tests__", "e2e")) and len(test_markers) < 40:
            test_markers.append(rel)

    frameworks: set[str] = set(detect_python_frameworks(requested_root))
    if package:
        deps: dict[str, Any] = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            value = package.get(key, {})
            if isinstance(value, dict):
                deps.update(value)
        for dep, label in FRAMEWORK_DEPS.items():
            if dep in deps:
                frameworks.add(label)

    existing_harness = []
    for rel in HARNESS_PATHS:
        path = requested_root / rel
        if path.exists():
            existing_harness.append(file_meta(path, requested_root))

    top_level = []
    try:
        for item in sorted(requested_root.iterdir(), key=lambda p: p.name.lower()):
            if item.name in {".git", "node_modules"}:
                continue
            kind = "symlink" if item.is_symlink() else "directory" if item.is_dir() else "file"
            top_level.append({"name": item.name, "kind": kind})
            if len(top_level) >= 100:
                break
    except OSError:
        pass

    git_status: list[str] = []
    if git_root:
        rc, output, _ = run(["git", "status", "--short"], requested_root)
        if rc == 0 and output:
            git_status = output.splitlines()[:100]

    root_hash = hashlib.sha256(str(requested_root).encode("utf-8")).hexdigest()[:12]
    data_root = (args.data_root or (Path.home() / ".claude" / "development-harness-data")).expanduser().resolve()
    staging_dir = data_root / "workspaces" / f"{requested_root.name}-{root_hash}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    scan_path = staging_dir / "project-scan.json"

    instructions_summary = {
        item["path"]: {k: v for k, v in item.items() if k not in {"path", "kind"}}
        for item in existing_harness
    }

    package_summary: dict[str, Any] | None = None
    if package:
        package_summary = {
            "name": package.get("name"),
            "private": package.get("private"),
            "packageManager": package.get("packageManager"),
            "workspaces": package.get("workspaces"),
            "scripts": sorted(package.get("scripts", {}).keys()) if isinstance(package.get("scripts"), dict) else [],
        }

    result = {
        "schema_version": 2,
        "requested_root": str(requested_root),
        "git_root": str(git_root) if git_root else None,
        "scope_relation": (
            "git-root" if git_root == requested_root else "inside-git-repository" if git_root else "not-a-git-repository"
        ),
        "workspace_key": root_hash,
        "staging_dir": str(staging_dir),
        "scan_path": str(scan_path),
        "repository_shape": detect_repo_shape(requested_root, package),
        "project_state": classify_project_state(
            top_level, manifests, language_counts, existing_harness
        ),
        "package_manager": pm,
        "package": package_summary,
        "languages": [
            {"name": name, "files": count}
            for name, count in language_counts.most_common(12)
        ],
        "frameworks_and_tools": sorted(frameworks),
        "manifests": sorted(set(manifests))[:100],
        "commands_detected": detect_commands(requested_root, package, pm),
        "top_level": top_level,
        "existing_harness": existing_harness,
        "instruction_file_summary": instructions_summary,
        "tests_detected": bool(test_markers),
        "test_markers": sorted(set(test_markers))[:40],
        "secret_bearing_files_exist": bool(secret_files),
        "secret_file_names_only": sorted(set(secret_files))[:40],
        "git_status": git_status,
        "tools": detect_tools(requested_root),
        "scanned_file_count_capped": scanned_files,
        "warnings": [
            "Detected commands are candidates, not proof that they succeed.",
            "Secret-bearing files were identified by name only and their contents were not read.",
        ],
    }

    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    scan_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()

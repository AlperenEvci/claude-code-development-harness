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
    ALLOWED_EFFORT,
    CAPABILITY_TIERS,
    CODEX_CONFIG_PATH,
    CODEX_SANDBOX_RANK,
    EDIT_ACCEPTING_MODES,
    codex_sandbox_floor,
    read_codex_config,
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

#: Installed only when the profile asked for `hooks_policy: guarded`. Kept
#: beside the tier lists rather than inside one, because hooks follow the policy
#: and not the tier.
HOOK_REQUIRED = [
    ".claude/settings.json",
    "scripts/ai-harness/hook_guard.py",
    "scripts/ai-harness/hook_session_start.py",
    "scripts/ai-harness/hook_precompact.py",
    "scripts/ai-harness/hook_stop.py",
]

FLEET_REQUIRED = [
    ".claude/skills/harness-codex-fleet/SKILL.md",
    ".ai/templates/lane-brief.md",
    ".ai/templates/ledger.md",
    "scripts/ai-harness/create-lane-worktree.sh",
]


#: The host vocabulary, the third copy of it. The renderer decides, the
#: validator re-derives before a package ships, and this one answers for a
#: repository somebody already installed and has since edited.
ALLOWED_HOSTS = ("claude-code", "codex", "opencode")
DEFAULT_HOSTS = ("claude-code",)
HOST_LABELS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
}

#: Codex truncates the AGENTS.md hierarchy here (`project_doc_max_bytes`).
CODEX_DOC_MAX_BYTES = 32 * 1024

#: The OpenCode surface, from `.ai/reports/0014-opencode-enforcement-surface.md`.
#: The guard plugin denies by throwing, and an agent file's permission block
#: removes the tool rather than refusing the call - so both are mechanisms this
#: script can look for, and their absence is reported as an absence.
OPENCODE_PLUGIN_PATH = ".opencode/plugins/harness-guard.js"
OPENCODE_AGENT_ROOT = ".opencode/agents"
OPENCODE_CONFIG_PATH = "opencode.json"

HOOK_CAPABLE_TIERS = frozenset({"standard", "fleet"})

#: The one flag each hook script takes, and the profile key its value must equal.
#: A separate copy of the validator's table: this is the only gate after the copy.
HOOK_COMMAND_ARGS = {
    "hook_session_start.py": ("--smoke", "smoke_command"),
    "hook_stop.py": ("--check", "smallest_check_command"),
}


def default_hooks_policy(tier: str) -> str:
    """Mirrors `render_harness.default_hooks_policy`; see the note there."""
    return "guarded" if str(tier).lower() in HOOK_CAPABLE_TIERS else "examples-only"


def hosts_of(profile: dict[str, Any]) -> list[str]:
    value = profile.get("hosts")
    if isinstance(value, list) and value:
        names = [str(item).strip().lower() for item in value]
        return [name for name in ALLOWED_HOSTS if name in names] or list(DEFAULT_HOSTS)
    return list(DEFAULT_HOSTS)


def host_guarantees(
    root: Path, profile: dict[str, Any], host: str
) -> list[tuple[str, str]]:
    """Say, for one host, which of this harness's guarantees actually fire there.

    Three values and no fourth: `present` means a mechanism on this machine
    enforces it, `absent` means nothing does, `unmeasured` means the host
    documents something the plugin has not yet exercised against a real run.
    A guarantee that a host cannot fire is reported, never rewritten as prose
    that nobody enforces - the rule decision 0005 carried from `.ai/reports/0012`.

    Evidence for the absences: `.ai/reports/0012-host-portability-smoke-test.md`
    (Codex hooks documented but never fired; OpenCode has no blocking stop event
    and no session-start injection) and `0013-skill-frontmatter-across-hosts.md`
    (neither other host honors `disable-model-invocation`), both in the plugin
    repository.
    """
    tier = str(profile.get("harness_tier", "standard")).lower()
    hooks_policy = str(profile.get("hooks_policy") or default_hooks_policy(tier))
    guarded = hooks_policy == "guarded" and (root / ".claude/settings.json").is_file()
    has_stop = guarded and bool(str(profile.get("smallest_check_command", "")).strip())

    if host == "claude-code":
        agents = "present" if tier in HOOK_CAPABLE_TIERS else "absent (tier installs none)"
        return [
            ("always-loaded contract", "present"),
            ("on-demand skills", "present"),
            ("manual-only skills", "present"),
            ("pre-tool-use guard", "present" if guarded else "absent (hooks not guarded)"),
            ("session-start brief", "present" if guarded else "absent (hooks not guarded)"),
            ("stop check", "present" if has_stop else "absent (no smallest check command)"),
            ("compaction boundary", "present" if guarded else "absent (hooks not guarded)"),
            ("read-only agent catalog", agents),
            (
                "permission floor",
                "absent (a tier is enforced by its launch flags, not by a settings floor)",
            ),
        ]

    if host == "codex":
        skills = (
            "present"
            if (root / ".agents/skills").is_dir()
            else "absent (.agents/skills is missing; Codex never reads .claude/skills)"
        )
        floor = read_codex_config(read_text(root / CODEX_CONFIG_PATH))
        codex_floor = (
            f"present ({floor['sandbox_mode']})"
            if floor["sandbox_mode"]
            else f"absent (no {CODEX_CONFIG_PATH} sandbox floor is installed)"
        )
        return [
            ("always-loaded contract", "present"),
            ("on-demand skills", skills),
            ("manual-only skills", "absent (not enforced on this host)"),
            ("pre-tool-use guard", "absent (no hook fired in six measured forms)"),
            ("session-start brief", "absent (no hook fired in six measured forms)"),
            ("stop check", "absent (no hook fired in six measured forms)"),
            ("compaction boundary", "absent (no hook fired in six measured forms)"),
            (
                "read-only agent catalog",
                "absent (a role's sandbox_mode binds nothing; measured 0.153.4)",
            ),
            ("permission floor", codex_floor),
        ]

    plugin = root / OPENCODE_PLUGIN_PATH
    if plugin.is_file():
        opencode_guard = "present"
    elif not guarded:
        opencode_guard = "absent (hooks not guarded)"
    else:
        opencode_guard = "absent (no guard plugin is installed)"

    agent_files = sorted((root / OPENCODE_AGENT_ROOT).glob("*.md"))
    opencode_agents = (
        "present" if agent_files else "absent (no read-only agent file is installed)"
    )

    try:
        opencode_floor = bool(
            json.loads(read_text(root / OPENCODE_CONFIG_PATH)).get("permission")
        )
    except ValueError:
        opencode_floor = False

    return [
        ("always-loaded contract", "present"),
        ("on-demand skills", "present"),
        ("manual-only skills", "absent (not enforced on this host)"),
        ("pre-tool-use guard", opencode_guard),
        ("session-start brief", "absent (this host has no session-start injection)"),
        ("stop check", "absent (this host has no blocking stop event)"),
        ("compaction boundary", "unmeasured (documented, not exercised)"),
        ("read-only agent catalog", opencode_agents),
        (
            "permission floor",
            "present" if opencode_floor else f"absent (no {OPENCODE_CONFIG_PATH} permission block)",
        ),
    ]


def hook_handler_args(settings_text: str) -> dict[str, list[str]] | None:
    """Map each registered harness hook script to the arguments after it.

    None when the file is not a JSON object with a `hooks` mapping. The shape is
    read loosely on purpose: this is the operator's file, possibly merged by hand,
    and the question is what it would run, not whether it is well-formed.
    """
    try:
        data = json.loads(settings_text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        return None
    found: dict[str, list[str]] = {}
    for groups in data["hooks"].values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            for handler in handlers or []:
                if not isinstance(handler, dict):
                    continue
                args = handler.get("args")
                if not isinstance(args, list) or not args:
                    continue
                script = str(args[0]).replace("\\", "/").rsplit("/", 1)[-1]
                if script.startswith("hook_") and script.endswith(".py"):
                    found[script] = [str(item) for item in args[1:]]
    return found


def check_hook_integrity(
    root: Path, profile: dict[str, Any], settings_text: str, errors: list[str]
) -> None:
    """The two hook invariants that survive installation, checked after it.

    The package validator proves them once, before the copy. Both the settings
    file and the scripts can be edited afterwards, and a hook runs before the
    permission check without asking the model, so what is on disk is what
    matters. Two things are checked, both errors:

    - a settings handler's flag value equals the profile's command byte for
      byte. `hook_stop.py --check` runs its value through a shell; a settings
      file and a profile that disagree mean one of them was changed after the
      operator approved the other, and the audit cannot tell which.
    - no installed hook script mentions a permission decision. A generated
      hook denies or adds context; one that allows is the untrusted-text rule
      broken by the one mechanism that runs unasked.
    """
    handlers = hook_handler_args(settings_text)
    if handlers is not None:
        for script, (flag, key) in HOOK_COMMAND_ARGS.items():
            if script not in handlers:
                continue
            extra = handlers[script]
            expected = str(profile.get(key, "")).strip()
            if not extra and not expected:
                continue
            if extra != [flag, expected] or not expected:
                errors.append(
                    f".claude/settings.json runs {script} with {extra}, but the "
                    f"profile's {key} is {expected!r}; one of the two was edited "
                    "after installation, and a hook may run only the command the "
                    "profile names - re-render rather than repair either by hand"
                )
    for name in HOOK_REQUIRED:
        if not name.endswith(".py"):
            continue
        text = read_text(root / name)
        if '"allow"' in text or "permissionDecision" in text:
            errors.append(
                f"{name} mentions a permission decision; a generated hook may deny, "
                "never allow - this copy was edited or replaced after installation"
            )


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

    # Effort is a warning here, not an error, and that is the difference between
    # this gate and the package validator. Before installation an unusable effort
    # is a defect in a package nobody is running yet. After installation the file
    # is live, an operator may have tuned it on purpose, and the harness has no
    # standing to call that a failure - but an effort the CLI will silently ignore
    # is still worth saying out loud, because nothing else will ever mention it.
    effort_match = re.search(r"^effort:\s*(\S+)\s*$", text, re.MULTILINE)
    if effort_match is None:
        warnings.append(f"agent declares no effort: {rel}")
    else:
        effort = effort_match.group(1).strip().strip("\"'").lower()
        if effort not in ALLOWED_EFFORT:
            warnings.append(
                f"agent effort {effort!r} is not one of {', '.join(ALLOWED_EFFORT)}; "
                f"the CLI ignores an unknown value and runs at its default: {rel}"
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


def check_shadowed_agents(
    root: Path,
    profile: dict[str, Any],
    dynamic: dict[str, dict[str, Any]],
    warnings: list[str],
) -> None:
    """Report an agent that is named like a generated one but is not one.

    Generated agents are the reviewed ones: their authority comes from the tier
    table, the renderer wrote them, and both the package validator and this
    checker hold them to it. They are also the ones an operator reaches for by
    name. A hand-added file called `harness-something` sits in the same directory,
    answers to the same naming convention, and carries none of that provenance -
    so the name is doing work the file has not earned.

    A warning rather than an error, deliberately. Adding an agent to your own
    repository is allowed and this checker has no business failing it; what it can
    do is refuse to let the file pass as generated. The authority such a file
    grants is a separate question, and `check_agent_authority` has already asked it.
    """
    generated = {rel for rel in dynamic if rel.startswith(".claude/agents/")}
    generated |= {rel for rel in STANDARD_REQUIRED if rel.startswith(".claude/agents/")}

    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return

    for path in sorted(agents_dir.glob("*.md")):
        rel = f".claude/agents/{path.name}"
        if rel in generated:
            continue
        if path.stem.startswith("harness-"):
            warnings.append(
                f"agent is named like a generated one but the profile does not "
                f"declare it, so it is not covered by the harness contract: {rel}"
            )


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
    check_shadowed_agents(root, profile, dynamic, warnings)
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
    hosts = hosts_of(profile)
    for name in profile.get("hosts") or []:
        if str(name).strip().lower() not in ALLOWED_HOSTS:
            errors.append(f"unknown host in project profile: {name!r}")
    if "codex" in hosts:
        required.append(".agents/skills/harness-orchestration/SKILL.md")
        if codex_sandbox_floor(profile):
            # The sandbox floor is the only thing a repository can enforce on
            # this host. A codex harness without it has a policy in prose and
            # nothing that fires.
            required.append(CODEX_CONFIG_PATH)
    hooks_policy = str(profile.get("hooks_policy") or default_hooks_policy(tier))
    if hooks_policy == "guarded":
        required.extend(HOOK_REQUIRED)
        if "opencode" in hosts:
            # The guard is this host's only pre-tool-use mechanism, so a guarded
            # profile that declares OpenCode and ships no plugin has a guarantee
            # its own contract claims and nothing enforces.
            required.append(OPENCODE_PLUGIN_PATH)
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

    surface = str(profile.get("session_surface", "inproc")).lower()
    if surface == "orca":
        claude_md = read_text(root / "CLAUDE.md")
        if claude_md and "### Watching a session in Orca" not in claude_md:
            errors.append(
                "profile configures session_surface=orca but the installed "
                "CLAUDE.md does not document the Orca surface"
            )
        # Absence is not an error. The surface is an operator convenience: the
        # harness works unchanged without it, and a teammate who does not run
        # Orca should get a note rather than a failing check.
        if shutil.which("orca") is None:
            warnings.append(
                "session_surface=orca but no orca command is on PATH; "
                "--surface orca cannot run here"
            )
        else:
            info.append("Orca session surface configured and orca found on PATH")
    elif surface != "inproc":
        errors.append(f"unknown session_surface: {surface}")

    host_status: dict[str, dict[str, str]] = {}
    for host in hosts:
        rows = host_guarantees(root, profile, host)
        host_status[host] = dict(rows)
        info.append(
            f"host {HOST_LABELS.get(host, host)}: "
            + "; ".join(f"{name} {state}" for name, state in rows)
        )

    agents_md = root / "AGENTS.md"
    if "codex" in hosts and agents_md.is_file():
        size = agents_md.stat().st_size
        if size >= CODEX_DOC_MAX_BYTES:
            errors.append(
                f"AGENTS.md is {size} bytes and a codex host is declared; Codex "
                f"reads at most {CODEX_DOC_MAX_BYTES} bytes of the AGENTS.md "
                "hierarchy, so the rest of the contract is dropped there"
            )

    # The mirror is only useful while it still says what the original says. An
    # installed repository has no path back to the plugin, so this compares the
    # two installed copies against each other rather than against a source.
    if "codex" in hosts:
        source_root = root / ".claude/skills"
        mirror_root = root / ".agents/skills"
        if source_root.is_dir() and mirror_root.is_dir():
            for source in sorted(source_root.rglob("*")):
                if not source.is_file():
                    continue
                rel = source.relative_to(source_root).as_posix()
                mirror = mirror_root / rel
                if not mirror.is_file():
                    errors.append(f"codex skill mirror is missing .agents/skills/{rel}")
                elif mirror.read_bytes() != source.read_bytes():
                    errors.append(
                        f".agents/skills/{rel} no longer matches .claude/skills/{rel}; "
                        "the two hosts read different instructions from one harness"
                    )

    if "codex" in hosts:
        config = root / CODEX_CONFIG_PATH
        if config.is_file():
            installed = read_codex_config(read_text(config))
            expected = codex_sandbox_floor(profile)
            actual_mode = installed["sandbox_mode"]
            if expected and actual_mode != expected["sandbox_mode"]:
                wider = CODEX_SANDBOX_RANK.get(actual_mode, 99) > CODEX_SANDBOX_RANK.get(
                    expected["sandbox_mode"], 0
                )
                message = (
                    f"{CODEX_CONFIG_PATH} sets sandbox_mode to {actual_mode!r} but "
                    f"the profile's autonomy implies {expected['sandbox_mode']!r}"
                )
                if wider:
                    # Report 0015: this file needs no flag and no trust prompt,
                    # so a widened floor silently hands the next `codex exec` in
                    # this repository more authority than the contract claims.
                    errors.append(
                        message + "; every codex session here now starts wider "
                        "than the harness says it may"
                    )
                else:
                    warnings.append(message)
            if (
                expected.get("network_access") is False
                and installed["network_access"] is True
            ):
                errors.append(
                    f"{CODEX_CONFIG_PATH} enables sandbox network access but the "
                    "profile's network policy denies it"
                )
            for role in installed["roles"]:
                warnings.append(
                    f"{CODEX_CONFIG_PATH} declares an agent role [agents.{role}]; "
                    "measured on Codex 0.153.4 a role's sandbox_mode binds nothing "
                    "in either direction, so this reads as a boundary and is not one"
                )

    if "opencode" in hosts:
        plugin = root / OPENCODE_PLUGIN_PATH
        if plugin.is_file():
            text = read_text(plugin)
            # Not a byte comparison: an installed repository has no path back to
            # the plugin that wrote this file. What can be checked from here is
            # that the two properties the guard's design rests on are still true.
            if "HARNESS_HOOKS_DISABLE" not in text:
                errors.append(
                    f"{OPENCODE_PLUGIN_PATH} no longer honors HARNESS_HOOKS_DISABLE; "
                    "a guard with no escape hatch cannot be stood down by the operator"
                )
            if "harnessDeny" not in text:
                warnings.append(
                    f"{OPENCODE_PLUGIN_PATH} has been edited: it no longer separates a "
                    "deliberate refusal from a defect, so a bug in it can now deny a "
                    "call that should have been allowed"
                )
        for agent in sorted((root / OPENCODE_AGENT_ROOT).glob("*.md")):
            text = read_text(agent)
            missing_lines = [
                line for line in ("edit: deny", "write: deny") if line not in text
            ]
            if missing_lines:
                errors.append(
                    f"{OPENCODE_AGENT_ROOT}/{agent.name} no longer declares "
                    f"{', '.join(missing_lines)}; on OpenCode that line is what removes "
                    "the tool, so the agent is no longer read-only"
                )
        config = root / OPENCODE_CONFIG_PATH
        if config.is_file():
            try:
                permission = json.loads(read_text(config)).get("permission")
            except ValueError:
                permission = None
                errors.append(f"{OPENCODE_CONFIG_PATH} is not readable JSON")
            if isinstance(permission, dict):
                tables = sorted(
                    tool for tool, value in permission.items() if isinstance(value, dict)
                )
                if tables:
                    warnings.append(
                        f"{OPENCODE_CONFIG_PATH} sets a per-command table for "
                        f"{', '.join(tables)}; measured on OpenCode 1.18.29 those do "
                        "not enforce under `opencode run`, so this reads as a rule and "
                        "is not one"
                    )

    settings_path = root / ".claude/settings.json"
    if settings_path.exists():
        text = read_text(settings_path)
        if "bypassPermissions" in text or "dangerously" in text:
            warnings.append("project Claude settings mention bypass/dangerous permissions; review manually")
        if hooks_policy == "guarded":
            # The settings file may be the operator's own, merged by hand after
            # the installer reported a conflict. Report what is actually wired
            # rather than assuming the rendered file survived.
            wired = ["hook_guard.py", "hook_session_start.py"]
            if str(profile.get("smallest_check_command", "")).strip():
                wired.append("hook_stop.py")
            missing = [name for name in wired if name not in text]
            if missing:
                warnings.append(
                    "hooks_policy is guarded but .claude/settings.json registers "
                    f"no handler for {', '.join(missing)}; if the installer "
                    "reported a conflict here, the hooks were never wired up"
                )
            else:
                info.append("Harness hooks are wired in .claude/settings.json")
            check_hook_integrity(root, profile, text, errors)
    elif hooks_policy == "guarded":
        errors.append(
            "hooks_policy is guarded but .claude/settings.json is absent; the "
            "installed hook scripts never run"
        )

    if hooks_policy == "guarded":
        for name in ("hook_guard.py", "hook_session_start.py", "hook_stop.py"):
            if not (root / "scripts/ai-harness" / name).is_file():
                errors.append(
                    f"hooks_policy is guarded but scripts/ai-harness/{name} is "
                    "missing; the settings file points at a script that is not there"
                )

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
        "hosts": host_status,
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

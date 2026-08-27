from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "development-harness"
SCRIPTS = PLUGIN / "scripts"


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def profile(tier: str) -> dict[str, object]:
    return {
        "project_name": f"Fixture {tier.title()}",
        "project_summary": "A disposable project used to verify harness rendering.",
        "project_stage": "mvp",
        "harness_mode": "adopt",
        "harness_tier": tier,
        "languages": ["TypeScript"],
        "frameworks": ["Next.js", "React"],
        "package_manager": "npm",
        "repository_shape": "single-project",
        "important_paths": ["src - product source", "test - automated tests"],
        "install_command": "npm ci",
        "dev_command": "npm run dev",
        "test_command": "npm test",
        "typecheck_command": "npm run typecheck",
        "lint_command": "npm run lint",
        "build_command": "npm run build",
        "full_gate_command": "npm run lint && npm run typecheck && npm test && npm run build",
        "main_orchestrator": "claude-code",
        "implementation_delegate": "codex-cli",
        "research_model": "opus",
        "review_model": "inherit",
        "codex_reasoning": "high",
        "autonomy": "repository-write-with-approval",
        "network_access": "deny-by-default",
        "hooks_policy": "disabled",
        "git_workflow": "feature-branches",
        "agent_commit_policy": "no-commit",
        "parallel_writes": tier == "fleet",
        "risk_level": "normal",
        "sensitive_areas": [],
        "project_rules": ["Business logic stays outside UI components."],
        "do_not_rules": ["Do not add dependencies without justification."],
        "commit_ai_reports": True,
        "commit_ai_runs": False,
        "generated_language": "English",
    }


def greenfield_profile(
    tier: str = "standard", setup_depth: str = "ready-to-build"
) -> dict[str, object]:
    data = profile(tier)
    data.update(
        {
            "project_name": "Greenfield Fixture",
            "project_summary": "A new product with no existing application code.",
            "project_stage": "idea",
            "harness_mode": "create",
            "repository_shape": "single-project",
            "important_paths": [
                "src - planned product source",
                "test - planned automated tests",
            ],
            "greenfield_context": {
                "setup_depth": setup_depth,
                "problem_statement": "The target users lack a reliable way to complete the core workflow.",
                "target_users": ["Primary operators"],
                "primary_outcome": "The user completes the core workflow end to end.",
                "mvp_goals": ["Deliver one working vertical slice"],
                "non_goals": ["No advanced analytics"],
                "core_workflows": ["Create and complete the primary work item"],
                "architecture_assumptions": ["Start as one deployable application"],
                "technical_constraints": ["No production secrets"],
                "external_integrations": [],
                "deployment_target": "Managed hosting",
                "initial_milestones": ["Scaffold and verify the first slice"],
                "open_questions": [],
                "blocking_questions": [],
                "create_root_readme": True,
                "git_initialization": "after-harness",
            },
        }
    )
    return data


class PluginStructureTests(unittest.TestCase):
    def test_manifests_are_valid_json_and_paths_exist(self) -> None:
        marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(marketplace["name"], "harness-tools")
        self.assertEqual(len(marketplace["plugins"]), 1)
        source = REPO / marketplace["plugins"][0]["source"]
        self.assertTrue(source.is_dir())
        self.assertNotIn("version", marketplace["plugins"][0])

        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "development-harness")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["version"], "0.2.0")

    def test_plugin_skills_are_explicit_and_reference_existing_scripts(self) -> None:
        for skill_name in ("setup", "audit"):
            path = PLUGIN / "skills" / skill_name / "SKILL.md"
            text = path.read_text()
            self.assertIn(f"name: {skill_name}", text)
            self.assertIn("disable-model-invocation: true", text)
            self.assertNotIn("${CLAUDE_SKILL_DIR}", text)

        setup = (PLUGIN / "skills" / "setup" / "SKILL.md").read_text()
        for script in ("inspect_project.py", "render_harness.py", "validate_harness.py", "check_installed.py"):
            self.assertIn(script, setup)
            self.assertTrue((SCRIPTS / script).is_file())
        self.assertIn("${CLAUDE_PLUGIN_DATA}/workspaces/*/generated/install-harness.sh", setup)
        self.assertIn("claude plugin list --json", setup)
        self.assertIn("codex-plugin", setup)
        self.assertIn("claude-only", setup)
        self.assertIn("Greenfield", setup)
        self.assertIn("project_state", setup)
        self.assertIn("context-only", setup)
        self.assertIn("ready-to-build", setup)

    def test_no_accidental_double_harness_prefix(self) -> None:
        needle = "harness-" + "harness"
        offenders: list[str] = []
        for path in REPO.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if needle in text:
                    offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [])


class InspectorTests(unittest.TestCase):
    def test_inspector_detects_project_and_never_emits_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = temp_path / "project"
            data = temp_path / "data"
            project.mkdir()
            (project / "package.json").write_text(
                json.dumps(
                    {
                        "name": "fixture-app",
                        "scripts": {
                            "dev": "next dev",
                            "test": "node --test",
                            "typecheck": "tsc --noEmit",
                            "build": "next build",
                        },
                        "dependencies": {"next": "latest", "react": "latest"},
                    }
                )
            )
            (project / "package-lock.json").write_text("{}")
            (project / "src").mkdir()
            (project / "src" / "index.ts").write_text("export const value: number = 1;\n")
            marker = "SUPER_SECRET_VALUE_SHOULD_NOT_APPEAR"
            (project / ".env.local").write_text(f"TOKEN={marker}\n")
            run("git", "init", cwd=project)

            result = run(
                "python3",
                str(SCRIPTS / "inspect_project.py"),
                "--root",
                str(project),
                "--data-root",
                str(data),
            )
            self.assertNotIn(marker, result.stdout)
            scan = json.loads(result.stdout)
            self.assertEqual(scan["package_manager"], "npm")
            self.assertIn("Next.js", scan["frameworks_and_tools"])
            self.assertIn("TypeScript", [item["name"] for item in scan["languages"]])
            self.assertTrue(scan["secret_bearing_files_exist"])
            self.assertIn(".env.local", scan["secret_file_names_only"])
            self.assertTrue(Path(scan["scan_path"]).is_file())
            self.assertTrue(str(Path(scan["scan_path"])).startswith(str(data)))
            self.assertEqual(scan["project_state"]["classification"], "existing")
            self.assertEqual(scan["project_state"]["suggested_harness_mode"], "adopt")

    def test_inspector_does_not_follow_repository_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = temp_path / "project"
            data = temp_path / "data"
            project.mkdir()
            outside = temp_path / "outside-package.json"
            marker = "OUTSIDE_SYMLINK_CONTENT_MUST_NOT_APPEAR"
            outside.write_text(
                json.dumps(
                    {
                        "name": marker,
                        "scripts": {"test": "echo should-not-be-read"},
                        "dependencies": {"next": "latest"},
                    }
                )
            )
            os.symlink(outside, project / "package.json")

            result = run(
                "python3",
                str(SCRIPTS / "inspect_project.py"),
                "--root",
                str(project),
                "--data-root",
                str(data),
            )
            self.assertNotIn(marker, result.stdout)
            scan = json.loads(result.stdout)
            self.assertIsNone(scan["package"])
            self.assertNotIn("Next.js", scan["frameworks_and_tools"])
            package_item = next(item for item in scan["top_level"] if item["name"] == "package.json")
            self.assertEqual(package_item["kind"], "symlink")

    def test_inspector_classifies_empty_folder_as_greenfield(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = temp_path / "blank-project"
            data = temp_path / "data"
            project.mkdir()
            result = run(
                "python3",
                str(SCRIPTS / "inspect_project.py"),
                "--root",
                str(project),
                "--data-root",
                str(data),
            )
            scan = json.loads(result.stdout)
            state = scan["project_state"]
            self.assertEqual(scan["schema_version"], 2)
            self.assertEqual(state["classification"], "empty")
            self.assertTrue(state["greenfield_candidate"])
            self.assertEqual(state["suggested_harness_mode"], "create")

    def test_inspector_treats_readme_only_folder_as_greenfield(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            project = temp_path / "planning-project"
            data = temp_path / "data"
            project.mkdir()
            (project / "README.md").write_text("# Product idea\n")
            result = run(
                "python3",
                str(SCRIPTS / "inspect_project.py"),
                "--root",
                str(project),
                "--data-root",
                str(data),
            )
            state = json.loads(result.stdout)["project_state"]
            self.assertEqual(state["classification"], "minimal-planning")
            self.assertTrue(state["greenfield_candidate"])
            self.assertEqual(state["suggested_harness_mode"], "create")


class RendererTests(unittest.TestCase):
    def render(self, temp_path: Path, tier: str) -> Path:
        config = temp_path / f"{tier}.json"
        output = temp_path / f"generated-{tier}"
        config.write_text(json.dumps(profile(tier), indent=2) + "\n")
        run(
            "python3",
            str(SCRIPTS / "render_harness.py"),
            "--config",
            str(config),
            "--output",
            str(output),
        )
        run("python3", str(SCRIPTS / "validate_harness.py"), str(output))
        return output

    def test_documented_example_profiles_render_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            for config in sorted((REPO / "examples").glob("*.json")):
                output = temp_path / config.stem
                run(
                    "python3",
                    str(SCRIPTS / "render_harness.py"),
                    "--config",
                    str(config),
                    "--output",
                    str(output),
                )
                run("python3", str(SCRIPTS / "validate_harness.py"), str(output))

    def test_all_tiers_render_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            for tier in ("lite", "standard", "fleet"):
                output = self.render(temp_path, tier)
                payload = output / "payload"
                self.assertTrue((output / ".development-harness-generated.json").is_file())
                self.assertTrue((payload / "AGENTS.md").is_file())
                self.assertTrue((payload / "CLAUDE.md").is_file())
                self.assertTrue((payload / ".ai/harness/project-profile.json").is_file())
                self.assertTrue((payload / ".claude/skills/harness-orchestration/SKILL.md").is_file())
                self.assertTrue((payload / ".claude/skills/harness-codex-delegate/SKILL.md").is_file())

                if tier in {"standard", "fleet"}:
                    self.assertTrue((payload / ".claude/agents/harness-codebase-researcher.md").is_file())
                    self.assertTrue((payload / ".claude/agents/harness-code-reviewer.md").is_file())
                else:
                    self.assertFalse((payload / ".claude/agents/harness-codebase-researcher.md").exists())

                if tier == "fleet":
                    helper = payload / "scripts/ai-harness/create-lane-worktree.sh"
                    self.assertTrue(helper.is_file())
                    self.assertTrue(helper.stat().st_mode & stat.S_IXUSR)
                    self.assertTrue((payload / ".claude/skills/harness-codex-fleet/SKILL.md").is_file())

    def test_greenfield_ready_to_build_renders_context_and_bootstrap_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            configured = greenfield_profile("standard", "ready-to-build")
            config = temp_path / "greenfield.json"
            output = temp_path / "greenfield-output"
            config.write_text(json.dumps(configured, indent=2) + "\n")
            run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
            )
            run("python3", str(SCRIPTS / "validate_harness.py"), str(output))
            payload = output / "payload"
            for rel in (
                "README.md",
                ".ai/project/brief.md",
                ".ai/project/architecture.md",
                ".ai/project/roadmap.md",
                ".ai/project/open-questions.md",
                ".ai/specs/current-task.md",
            ):
                self.assertTrue((payload / rel).is_file(), rel)
            self.assertIn("Greenfield startup", (payload / "CLAUDE.md").read_text())
            self.assertIn("planned architecture", (payload / ".ai/README.md").read_text())
            self.assertIn(
                "No meaningful application codebase is assumed",
                (payload / ".ai/specs/current-task.md").read_text(),
            )

    def test_greenfield_context_only_omits_bootstrap_spec_and_optional_readme(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            configured = greenfield_profile("lite", "context-only")
            configured["greenfield_context"]["create_root_readme"] = False
            config = temp_path / "greenfield-context-only.json"
            output = temp_path / "greenfield-context-only-output"
            config.write_text(json.dumps(configured, indent=2) + "\n")
            run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
            )
            run("python3", str(SCRIPTS / "validate_harness.py"), str(output))
            payload = output / "payload"
            self.assertFalse((payload / "README.md").exists())
            self.assertFalse((payload / ".ai/specs/current-task.md").exists())
            self.assertTrue((payload / ".ai/project/brief.md").is_file())
            self.assertIn(
                "No implementation contract was generated",
                (payload / ".ai/backlog.md").read_text(),
            )

    def test_greenfield_rejects_fleet_and_missing_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            cases = []
            fleet = greenfield_profile("fleet", "ready-to-build")
            cases.append((fleet, "cannot start at Fleet"))
            missing = profile("lite")
            missing["harness_mode"] = "create"
            cases.append((missing, "requires a greenfield_context"))
            blocked = greenfield_profile("lite", "ready-to-build")
            blocked["greenfield_context"]["blocking_questions"] = ["Choose database"]
            cases.append((blocked, "requires blocking_questions to be empty"))

            for index, (configured, expected) in enumerate(cases):
                config = temp_path / f"greenfield-invalid-{index}.json"
                config.write_text(json.dumps(configured, indent=2) + "\n")
                result = run(
                    "python3",
                    str(SCRIPTS / "render_harness.py"),
                    "--config",
                    str(config),
                    "--output",
                    str(temp_path / f"greenfield-invalid-output-{index}"),
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_official_codex_plugin_transport_renders_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            configured = profile("standard")
            configured["implementation_delegate"] = "codex-plugin"
            config = temp_path / "plugin.json"
            output = temp_path / "plugin-output"
            config.write_text(json.dumps(configured, indent=2) + "\n")
            run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
            )
            run("python3", str(SCRIPTS / "validate_harness.py"), str(output))
            skill = (
                output
                / "payload/.claude/skills/harness-codex-delegate/SKILL.md"
            ).read_text()
            self.assertIn("Configured transport: `codex-plugin`", skill)
            self.assertIn("codex:codex-rescue", skill)
            self.assertIn("openai/codex-plugin-cc", skill)
            self.assertNotIn("codex exec", skill)

    def test_claude_only_transport_omits_codex_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            configured = profile("standard")
            configured["implementation_delegate"] = "claude-only"
            config = temp_path / "claude-only.json"
            output = temp_path / "claude-only-output"
            config.write_text(json.dumps(configured, indent=2) + "\n")
            run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
            )
            run("python3", str(SCRIPTS / "validate_harness.py"), str(output))
            payload = output / "payload"
            self.assertFalse(
                (payload / ".claude/skills/harness-codex-delegate/SKILL.md").exists()
            )
            orchestration = (
                payload / ".claude/skills/harness-orchestration/SKILL.md"
            ).read_text()
            self.assertIn("bounded Claude implementation", orchestration)
            docs = (payload / "docs/ai-harness/README.md").read_text()
            self.assertIn("Configured transport: `claude-only`", docs)

    def test_fleet_rejects_non_cli_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            for delegate in ("codex-plugin", "claude-only"):
                configured = profile("fleet")
                configured["implementation_delegate"] = delegate
                config = temp_path / f"fleet-{delegate}.json"
                config.write_text(json.dumps(configured, indent=2) + "\n")
                result = run(
                    "python3",
                    str(SCRIPTS / "render_harness.py"),
                    "--config",
                    str(config),
                    "--output",
                    str(temp_path / f"fleet-{delegate}-output"),
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Fleet tier", result.stderr)
                self.assertIn("codex-cli", result.stderr)

    def test_install_new_only_preserves_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            output = self.render(temp_path, "standard")
            target = temp_path / "target"
            target.mkdir()
            original = "# Existing human contract\n"
            (target / "AGENTS.md").write_text(original)

            dry = run(str(output / "install-harness.sh"), "--target", str(target), "--dry-run")
            self.assertIn("CONFLICT  AGENTS.md", dry.stdout)
            self.assertIn("Dry run only", dry.stdout)
            self.assertFalse((target / "CLAUDE.md").exists())

            apply = run(str(output / "install-harness.sh"), "--target", str(target), "--apply-new-only")
            self.assertIn("SKIPPED   AGENTS.md (conflict)", apply.stdout)
            self.assertEqual((target / "AGENTS.md").read_text(), original)
            self.assertTrue((target / "CLAUDE.md").is_file())

            check = run(
                "python3",
                str(SCRIPTS / "check_installed.py"),
                "--root",
                str(target),
                check=False,
            )
            self.assertEqual(check.returncode, 0, msg=check.stdout + check.stderr)
            self.assertNotIn("unsafe/default-bypass", check.stdout + check.stderr)

    def test_explicit_overwrite_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            output = self.render(temp_path, "lite")
            target = temp_path / "target"
            target.mkdir()
            original = "# Existing contract\n"
            (target / "AGENTS.md").write_text(original)

            run(str(output / "install-harness.sh"), "--target", str(target), "--backup-and-overwrite")
            self.assertNotEqual((target / "AGENTS.md").read_text(), original)
            backups = list((target / ".harness-backups").rglob("AGENTS.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)

    def test_project_specific_components_render_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            custom = profile("standard")
            custom["scoped_rules"] = [
                {
                    "name": "frontend-boundaries",
                    "description": "Frontend boundaries",
                    "paths": ["src/app/**", "src/components/**"],
                    "instructions": ["Keep server-only logic out of client components."],
                }
            ]
            custom["additional_skills"] = [
                {
                    "name": "release-readiness",
                    "description": "Run release readiness checks without deploying",
                    "manual_only": True,
                    "argument_hint": "[optional release context]",
                    "instructions": ["Read the current diff.", "Run configured gates."],
                }
            ]
            custom["additional_agents"] = [
                {
                    "name": "billing-researcher",
                    "description": "Map billing behavior without editing",
                    "model": "inherit",
                    "max_turns": 24,
                    "instructions": ["Return evidence and unresolved billing risks."],
                }
            ]
            config = temp_path / "custom.json"
            output = temp_path / "custom-output"
            config.write_text(json.dumps(custom, indent=2) + "\n")
            run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
            )
            run("python3", str(SCRIPTS / "validate_harness.py"), str(output))
            payload = output / "payload"
            self.assertTrue((payload / ".claude/rules/harness-frontend-boundaries.md").is_file())
            self.assertTrue((payload / ".claude/skills/harness-release-readiness/SKILL.md").is_file())
            agent = payload / ".claude/agents/harness-billing-researcher.md"
            self.assertTrue(agent.is_file())
            agent_text = agent.read_text()
            self.assertIn("permissionMode: plan", agent_text)
            self.assertIn('model: "inherit"', agent_text)
            self.assertIn("  - Bash", agent_text)
            skill_text = (payload / ".claude/skills/harness-release-readiness/SKILL.md").read_text()
            self.assertIn("disable-model-invocation: true", skill_text)
            self.assertNotIn("allowed-tools:", skill_text)
            delegate = (payload / ".claude/skills/harness-codex-delegate/SKILL.md").read_text()
            self.assertIn('- < "${CLAUDE_PROJECT_DIR}/.ai/specs/current-task.md"', delegate)
            self.assertNotIn("$(cat", delegate)

    def test_custom_components_cannot_preapprove_tools_or_override_agent_security(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            cases = []

            skill_profile = profile("standard")
            skill_profile["additional_skills"] = [
                {
                    "name": "unsafe-skill",
                    "description": "Unsafe test",
                    "allowed_tools": ["Bash"],
                    "instructions": ["Run something."],
                }
            ]
            cases.append((skill_profile, "may not pre-approve tools"))

            agent_profile = profile("standard")
            agent_profile["additional_agents"] = [
                {
                    "name": "unsafe-agent",
                    "description": "Unsafe test",
                    "tools": ["Read", "Bash"],
                    "instructions": ["Investigate."],
                }
            ]
            cases.append((agent_profile, "may not override security fields"))

            for index, (case, expected) in enumerate(cases):
                config = temp_path / f"unsafe-{index}.json"
                config.write_text(json.dumps(case, indent=2) + "\n")
                result = run(
                    "python3",
                    str(SCRIPTS / "render_harness.py"),
                    "--config",
                    str(config),
                    "--output",
                    str(temp_path / f"unsafe-output-{index}"),
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_force_refuses_unrecognized_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            config = temp_path / "profile.json"
            config.write_text(json.dumps(profile("lite"), indent=2) + "\n")
            output = temp_path / "do-not-delete"
            output.mkdir()
            sentinel = output / "human-file.txt"
            sentinel.write_text("preserve me\n")
            result = run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
                "--force",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to delete unrecognized directory", result.stderr)
            self.assertEqual(sentinel.read_text(), "preserve me\n")

    def test_force_replaces_only_a_previous_generated_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            config = temp_path / "profile.json"
            config.write_text(json.dumps(profile("lite"), indent=2) + "\n")
            output = temp_path / "generated"
            command = (
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(output),
            )
            run(*command)
            marker = output / ".development-harness-generated.json"
            self.assertTrue(marker.is_file())
            (output / "stale.txt").write_text("stale\n")
            run(*command, "--force")
            self.assertFalse((output / "stale.txt").exists())
            self.assertTrue(marker.is_file())

    def test_installer_refuses_symlinked_destination_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            output = self.render(temp_path, "standard")
            target = temp_path / "target"
            outside = temp_path / "outside"
            target.mkdir()
            outside.mkdir()
            os.symlink(outside, target / ".claude")

            dry = run(str(output / "install-harness.sh"), "--target", str(target), "--dry-run")
            self.assertIn("BLOCKED", dry.stdout)
            self.assertIn("symlink path component", dry.stdout)

            apply = run(
                str(output / "install-harness.sh"),
                "--target",
                str(target),
                "--apply-new-only",
                check=False,
            )
            self.assertNotEqual(apply.returncode, 0)
            self.assertFalse((outside / "skills").exists())
            self.assertFalse((target / "AGENTS.md").exists())

    def test_validator_rejects_unsafe_codex_command_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            output = self.render(temp_path, "lite")
            delegate = output / "payload/.claude/skills/harness-codex-delegate/SKILL.md"
            text = delegate.read_text()
            text = text.replace("--sandbox workspace-write", "--sandbox danger-full-access", 1)
            delegate.write_text(text)

            result = run(
                "python3",
                str(SCRIPTS / "validate_harness.py"),
                str(output),
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe Codex default token in executable block", result.stderr)
            self.assertIn("danger-full-access", result.stderr)

    def test_invalid_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            bad = profile("standard")
            bad["implementation_delegate"] = "unknown-agent"
            config = temp_path / "bad.json"
            config.write_text(json.dumps(bad))
            result = run(
                "python3",
                str(SCRIPTS / "render_harness.py"),
                "--config",
                str(config),
                "--output",
                str(temp_path / "out"),
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implementation_delegate", result.stderr)


if __name__ == "__main__":
    unittest.main()

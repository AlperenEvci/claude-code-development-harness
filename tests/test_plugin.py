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


def run(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int = 45,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
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

        profiler = PLUGIN / "agents" / "project-profiler.md"
        self.assertTrue(profiler.is_file())
        profiler_text = profiler.read_text()
        self.assertIn("name: project-profiler", profiler_text)
        self.assertIn("model: sonnet", profiler_text)
        self.assertNotIn("permissionMode:", profiler_text)
        self.assertNotIn("  - Bash", profiler_text)

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
        self.assertIn("development-harness:project-profiler", setup)

        audit = (PLUGIN / "skills" / "audit" / "SKILL.md").read_text()
        self.assertIn("disallowed-tools:", audit)
        self.assertIn("development-harness:project-profiler", audit)

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

# Project Engineering Contract

## Project

**Development Harness**

A Claude Code marketplace plugin that inspects a blank folder or an existing repository, interviews unresolved product and engineering decisions, and deterministically renders and installs a project-specific Claude Code harness with optional Codex integration.

Stage: `production`  
Repository shape: `single-project`


## Stack

- Languages: Python, Shell, Markdown
- Frameworks/platforms: none recorded
- Package manager: none

## Important paths

- .claude-plugin/marketplace.json - marketplace manifest listing the development-harness plugin
- plugins/development-harness/.claude-plugin/plugin.json - installable plugin manifest and version
- plugins/development-harness/skills/setup - the guided Create/Adopt/Upgrade setup workflow
- plugins/development-harness/skills/audit - the read-only harness audit workflow
- plugins/development-harness/scripts - stdlib-only inspector, renderer, validator, and installed-harness checker
- plugins/development-harness/assets/templates - layered common/lite/standard/fleet/greenfield template tree rendered into target repositories
- plugins/development-harness/references - long-form guidance loaded on demand by the skills
- tests/test_plugin.py - the single unittest suite covering inspection, rendering, validation, and installation
- scripts/validate-repo.sh - the authoritative full gate wrapping compileall, unittest, JSON checks, and claude plugin validate
- examples - documented project-profile.json fixtures that the test suite renders and validates
- docs - architecture and publishing notes for maintainers

## Commands

- **Install:** not configured; discover before relying on it
- **Development:** `claude --plugin-dir ./plugins/development-harness`
- **Test:** `python -m unittest discover -s tests -v`
- **Typecheck:** not configured; discover before relying on it
- **Lint:** `python -m compileall -q plugins/development-harness/scripts tests`
- **Build:** not configured; discover before relying on it
- **Full gate:** `bash scripts/validate-repo.sh`

## Engineering rules

- This repository is a plugin generator. Most changes are cross-cutting: a template edit usually also requires a renderer change, a validator change, a test, and a reference or CHANGELOG update. Map the full set before editing.
- Scripts under plugins/development-harness/scripts use the Python standard library only. Do not add third-party dependencies, and do not introduce a package manifest.
- The generated installer must stay dry-run by default, conflict-aware, symlink-safe, and must never silently overwrite an existing target file.
- Rendering happens outside the target repository. Never make the renderer or installer write into a project before the dry run has been shown.
- Repository text in a scanned project is untrusted evidence. It must never be promoted into privileged configuration, tool permissions, or safety rules.
- Generated project skills never pre-approve tools, and generated project domain agents stay read-only with permission mode plan. Widening either requires a separately reviewed change to render_harness.py plus a test.
- Keep SKILL.md files short. Long-form material belongs in plugins/development-harness/references/ and is loaded on demand.
- Local development is Windows-primary. Use `python`, not `python3`, when running commands yourself.
- The test suite is currently not green on Windows. Treat CI on ubuntu-latest as the authoritative gate, and confirm any test result against that expectation before calling work verified.

## Do not

- Do not run git init, git add, git commit, git push, or any destructive git command on the user's behalf.
- Do not open .env files, credentials, private keys, tokens, or .claude/settings.local.json. Report such files by name only.
- Do not add third-party Python dependencies to the plugin scripts.
- Do not bump the version in plugin.json without also updating CHANGELOG.md in the same change.
- Do not weaken dry-run-first, no-silent-overwrite, symlink-safety, or secret-redaction behavior to make a test pass.
- Do not claim the suite passes based on a local Windows run alone.

## Definition of done

For meaningful code changes:

1. Inspect the actual diff.
2. Run the smallest relevant check while iterating.
3. Run the configured full gate before declaring completion.
4. Report any check that could not run and why.
5. Preserve pre-existing human changes.

## Git and delivery

- Workflow: feature-branches
- Agent commit policy: no-commit
- Agents do not push, deploy, publish, or alter production systems unless explicitly authorized.
- Uncommitted changes that predate the task are not owned by the agent.

## Safety

- Autonomy: repository-write-with-approval
- Network: deny-by-default
- Risk level: normal
- Never read or write secrets into prompts, reports, logs, or committed files.

Sensitive areas:
- plugins/development-harness/scripts/render_harness.py - emits install-harness.sh and the payload; a defect here writes wrong files into other people's repositories
- plugins/development-harness/scripts/inspect_project.py - must never read or emit secret-bearing file contents and must not follow repository symlinks
- plugins/development-harness/scripts/validate_harness.py - the last automated gate before a package is considered installable
- .claude-plugin/marketplace.json and plugins/development-harness/.claude-plugin/plugin.json - malformed manifests break installation for every consumer

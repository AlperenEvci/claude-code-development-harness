# AI Development Harness

Project: **Development Harness**  
Tier: **standard**  
Mode: **adopt**

## Purpose

This harness makes context, delegation, artifacts, permissions, and verification explicit across Claude Code roles.


## Roles

| Role | Owns | Output |
|---|---|---|
| Main Claude | judgment, architecture, synthesis, spec, final gate | decisions, specs, verified result |
| Researcher | codebase evidence | report |
| Claude implementation | bounded execution against an accepted contract | diff and check results |
| Reviewer | independent verification | verdict and findings |

## Task routing

- Trivial: direct change and direct check.
- Standard: optional research → synthesis → spec → bounded Claude implementation → independent verification.
- Complex: parallel read-only research → decisions → bounded specs → isolated write lanes when installed → integration gate.

## Files

- `AGENTS.md`: shared engineering contract.
- `CLAUDE.md`: Claude-specific orchestration.
- `.claude/agents/`: isolated Claude workers.
- `.claude/skills/`: on-demand workflows.
- `.ai/`: project memory and handoff artifacts.

## Implementation transport

Configured transport: `claude-only`.

No Codex-specific project skill is installed. Claude still uses the same evidence, decision, spec, scope, and independent-verification discipline.

## Project-specific extensions

- Rule `harness-templates`: Rules for the layered harness template tree
- Rule `harness-generator-scripts`: Safety invariants for the inspector, renderer, validator, and checker
- Rule `harness-plugin-surface`: Rules for skill definitions, references, and plugin manifests
- Skill `harness-release-bump`: Perform a coordinated version bump of the development-harness plugin across the manifest, changelog, and any version-bearing documentation, then run the full gate. Invoke explicitly when cutting a new plugin release.
- Skill `harness-fixture-smoke-test`: Exercise the setup pipeline end to end against a disposable fixture repository outside this project, to prove that inspection, rendering, validation, and dry-run installation still work together. Invoke explicitly after changing templates, the renderer, the validator, or the installer.
- Agent `harness-template-cartographer`: Read-only researcher that maps the layered harness template tree and traces where a placeholder, template file, or generated artifact is produced, validated, and asserted. Use before editing templates, the renderer, or the validator, when you need the full blast radius of a change rather than a single file.

## Installation policy

The generated installer is non-destructive by default. Always run dry-run first. New-files-only mode skips conflicts. Backup-and-overwrite mode requires an explicit flag.

## Maintenance

Update the smallest relevant surface when:

- the same failure happens twice,
- commands or architecture change,
- a rule becomes stale,
- context files grow too large,
- orchestration cost exceeds value.

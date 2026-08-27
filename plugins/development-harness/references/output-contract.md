# Output Quality Contract

A high-quality result is complete only when all sections below exist.

## 1. Diagnosis

State:

- what currently exists,
- what is missing,
- what should be preserved,
- contradictions or unsafe settings,
- assumptions caused by missing evidence.

## 2. Design decision

Explain why the chosen tier is sufficient and why the next tier is unnecessary.

## 3. Role map

Name each role, its context boundary, tool permissions, and output:

| Role | Owns | Must not own | Output |
|---|---|---|---|
| Main orchestrator | judgment, synthesis, spec, final gate | noisy bulk exploration | decisions/spec/final result |
| Researcher | evidence and mapping | implementation | report |
| Codex delegate | scoped implementation | product decisions | diff + command results |
| Reviewer | independent verification | feature editing | findings |

Adapt this table to the project.

## 4. File map

For each generated file explain:

- why it exists,
- whether it is always loaded or on-demand,
- whether it should be committed,
- who updates it.

## 5. Install package

The package must contain:

- `payload/` with generated repository files,
- `project-profile.json`,
- `harness-manifest.json`,
- `install-harness.sh`,
- `README.md`.

The installer must support:

```bash
./install-harness.sh --target /repo --dry-run
./install-harness.sh --target /repo --apply-new-only
./install-harness.sh --target /repo --backup-and-overwrite
```

Default to dry-run. Never silently overwrite.

## 6. Verification

Include product-specific checks plus harness discovery checks.

The smoke test should be small enough to inspect but complex enough to prove:

- a skill routes the task,
- research can run in isolated context,
- a self-contained spec is generated,
- Codex can execute it,
- the main agent independently verifies it.

## 7. Maintenance

State the concrete trigger for changing each instruction surface. Avoid generic "keep docs updated" language.

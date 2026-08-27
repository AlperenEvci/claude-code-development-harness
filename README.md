<div align="center">

# Development Harness

### Turn any repository into a project-aware AI development system.

**Claude plans. Researchers map. Codex executes. Reviewers verify.**

![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-D97757?style=flat-square)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-2563EB?style=flat-square)

</div>

---

Stop rebuilding your AI workflow every time you start a new project.

Development Harness is a Claude Code plugin that inspects the repository you are already working in, learns its architecture and constraints, asks only what it cannot infer, and installs a **project-specific development harness** directly into that repository.

One command turns an ordinary codebase into a structured multi-agent workflow with clear roles, durable project memory, explicit implementation contracts, and independent verification:

```text
/development-harness:setup
```

> **The main context should be a boardroom, not a warehouse.**
>
> Raw exploration belongs in isolated agents. Decisions, specifications, and verified outcomes belong in the main session.

## Why use it?

Without a harness, every new Claude Code session tends to repeat the same expensive work:

- rediscover the repository,
- mix research, architecture, implementation, and review in one context,
- lose decisions after compaction or session changes,
- delegate vague tasks that produce inconsistent code,
- trust an agent's “done” message without independently verifying the result.

Development Harness gives the project a repeatable operating model:

```text
Repository evidence
        ↓
Focused research
        ↓
Main-agent synthesis and decisions
        ↓
Self-contained implementation spec
        ↓
Claude or Codex execution
        ↓
Independent verification
        ↓
Durable project knowledge
```

It is not a generic folder template. The generated harness is adapted to the current repository, its stack, its risk profile, its test gates, and the way you want Claude and Codex to collaborate.

## Quick start

Run these commands inside Claude Code:

```text
/plugin marketplace add egecan-af/claude-development-harness
/plugin install development-harness@harness-tools
/reload-plugins
```

Open the project you want to configure and run:

```text
/development-harness:setup
```

You can include context immediately:

```text
/development-harness:setup Existing Next.js MVP. Claude should own architecture and specs; Codex should implement. No network access, automatic commits, or deploys. Prefer a Standard harness.
```

The plugin will inspect the repository first, then ask only the unresolved questions in small batches.

## What happens during setup?

```text
Current repository
       │
       ▼
Read-only inspection
       │
       ▼
Short adaptive interview
       │
       ▼
Lite / Standard / Fleet selection
       │
       ▼
Project-specific harness generated outside the repo
       │
       ▼
Validation + dry-run + conflict analysis
       │
       ▼
Safe installation into the project
       │
       ▼
Discovery and verification checks
```

The setup process detects, where available:

- languages, frameworks, package manager, and repository shape,
- real test, lint, typecheck, and build commands,
- existing `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`, and `.ai/` structures,
- Git state and project boundaries,
- local Claude Code and Codex capabilities,
- filenames that may contain secrets, without opening their contents.

Repository content is treated as evidence—not as an instruction source that can override the plugin.

## What gets installed?

A typical Standard harness looks like this:

```text
project/
├── AGENTS.md
├── CLAUDE.md
├── .claude/
│   ├── agents/
│   │   ├── harness-codebase-researcher.md
│   │   └── harness-code-reviewer.md
│   ├── rules/
│   │   └── project-specific-rules.md
│   └── skills/
│       ├── harness-orchestration/
│       │   └── SKILL.md
│       └── harness-codex-delegate/
│           └── SKILL.md
├── .ai/
│   ├── README.md
│   ├── backlog.md
│   ├── harness/
│   │   └── project-profile.json
│   ├── reports/
│   ├── decisions/
│   ├── specs/
│   ├── runs/
│   └── templates/
└── docs/
    └── ai-harness/
        └── README.md
```

The exact output depends on the project. The plugin can also generate evidence-backed additions such as:

- path-scoped rules for sensitive domains or directories,
- reusable workflows for recurring project operations,
- read-only domain researchers for complex areas of the codebase.

It deliberately does **not** create one agent per folder or add speculative machinery without a concrete reason.

## Three harness tiers

| Tier | Best for | What it adds |
|---|---|---|
| **Lite** | prototypes, small repositories, weak or incomplete test gates | shared contracts, orchestration, selected implementation path, `.ai/` knowledge structure |
| **Standard** | serious MVPs and production products | focused codebase researcher, independent reviewer, stronger specification and verification flow |
| **Fleet** | repeated, genuinely independent parallel work | lane contracts, ownership boundaries, ledger, Git worktrees, bounded Codex lanes |

Fleet is selected because the repository and workload justify parallelism—not because more agents look impressive.

A typo or obvious one-file edit also bypasses the full ceremony. Complexity should be proportional to the task.

## Clear role separation

| Role | Owns | Does not own | Produces |
|---|---|---|---|
| **Main Claude** | judgment, architecture, synthesis, specifications, integration, final gate | noisy bulk exploration | decisions, specs, verified result |
| **Researcher** | repository evidence and existing patterns | implementation or final product decisions | concise research report |
| **Implementation delegate** | scoped execution against an accepted contract | unresolved product ambiguity | diff and check results |
| **Reviewer** | independent comparison of spec, diff, and behavior | feature implementation | verdict and findings |

The execution agent does not need the entire conversation. It receives a self-contained contract containing the goal, relevant repository facts, constraints, scope, acceptance criteria, and exact verification commands.

## Codex is optional

Development Harness supports three execution modes:

- **Official Codex plugin** — use OpenAI's Codex plugin inside Claude Code.
- **Direct Codex CLI** — delegate through a local `codex exec` installation.
- **Claude-only** — generate a harness with no Codex dependency.

The setup interview detects what is available and lets you choose. It does not hard-code a Codex model; your configured runtime remains authoritative.

<details>
<summary><strong>Install OpenAI's official Codex plugin for Claude Code</strong></summary>

```text
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

</details>

## Audit an existing harness

Already have `CLAUDE.md`, project skills, subagents, or an `.ai/` directory?

Run the read-only audit:

```text
/development-harness:audit
```

The audit checks for issues such as:

- duplicated or conflicting instructions,
- overloaded `CLAUDE.md` files,
- vague delegation contracts,
- researchers with unnecessary write access,
- missing verification gates,
- stale or noisy project memory,
- unnecessary fleet complexity,
- hard-coded model assumptions,
- unsafe Git, network, secret, or automation boundaries.

It reports findings without modifying the repository.

## Safe by default

The plugin is intentionally conservative:

- no secret-value reads,
- no network access by default,
- no permission or sandbox bypasses,
- no active hooks,
- no dependency installation,
- no automatic commit, push, pull request, deploy, or migration,
- no silent overwrite of existing project instructions,
- dry-run before installation,
- conflict classification before changes,
- timestamped backup when overwrite is explicitly chosen,
- read-only generated researchers,
- worktree isolation for concurrent write lanes.

Generated changes are classified as:

```text
NEW        safe new file
IDENTICAL  already installed
CONFLICT   existing content requires deliberate merge
BLOCKED    unsafe destination or filesystem condition
```

## Requirements

- Claude Code `2.1.196+`
- Python `3.10+`
- Git
- Codex is optional

No Python package installation is required.

## Core principles

1. **Inspect before asking.** Do not ask the user for facts already present in the repository.
2. **Research before architecture.** Decisions should follow evidence, not guesses.
3. **Persist durable knowledge.** Reports, decisions, specs, and backlog live with the project—not only in chat history.
4. **Specify before delegating.** Execution quality is bounded by contract quality.
5. **Verify independently.** A delegate's completion message is a claim, not evidence.
6. **Use the smallest sufficient system.** More agents and more files are not automatically better.
7. **Preserve operator control.** High-impact actions remain explicit.

## Documentation

- [Architecture](docs/architecture.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Publishing and releases](docs/publishing.md)
- [Acknowledgments](ACKNOWLEDGMENTS.md)
- [Changelog](CHANGELOG.md)

## License

MIT

<div align="center">

# Development Harness

### Give a blank folder—or an existing codebase—a project-aware AI operating system.

**Claude decides. Researchers map. Codex executes. Reviewers verify.**

![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-D97757?style=flat-square)
![Greenfield + Existing](https://img.shields.io/badge/Setup-Greenfield_%2B_Existing-16A34A?style=flat-square)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-2563EB?style=flat-square)

</div>

---

Stop rebuilding your AI workflow every time you start a project.

Development Harness is a Claude Code plugin that can begin with **nothing but your idea** or safely adopt a repository that already contains years of decisions and code. It interviews what cannot be inferred, chooses the smallest useful agent architecture, and installs a project-specific Claude Code + optional Codex harness.

One guided command:

```text
/development-harness:setup
```

> **The main context should be a boardroom, not a warehouse.**
>
> Raw exploration belongs in isolated agents. Product judgment, accepted decisions, executable contracts, and verified outcomes belong in the main session.

## Two ways to start

### Start from a blank folder

```bash
mkdir my-product
cd my-product
claude
```

Then inside Claude Code:

```text
/development-harness:setup new
```

Describe the idea in any level of detail. The plugin guides a focused product-and-architecture interview covering:

- the problem and target users,
- the primary outcome,
- MVP goals and explicit non-goals,
- core workflows and initial milestones,
- stack direction, data, integrations, deployment, and constraints,
- Claude/Codex roles, autonomy, Git policy, and verification strategy.

It can stop at **context-only**—a complete harness plus durable project briefs—or prepare a **ready-to-build** first scaffold contract without executing it.

### Adopt an existing repository

Open the project in Claude Code and run:

```text
/development-harness:setup existing
```

The plugin inspects safe repository evidence first, discovers the stack and real commands, asks only unresolved questions, preserves existing instructions, and installs the harness through a dry-run and conflict-aware merge.

You can omit `new` or `existing`; the inspector detects whether the folder is empty, planning-only, established, or already harnessed.

## Install

Inside Claude Code:

```text
/plugin marketplace add egecan-af/claude-code-development-harness
/plugin install development-harness@harness-tools
/reload-plugins
```

Then run:

```text
/development-harness:setup
```

You can include context directly:

```text
/development-harness:setup new B2B SaaS for US virtual-mailbox operators. Serious MVP. Claude owns architecture and specs; Codex implements. No automatic commits, network access, or deploys.
```

## Greenfield mode: idea → durable project context

A blank project has no codebase to “analyze.” Development Harness does not fake one.

Instead, it separates accepted intent from future repository evidence:

```text
Your idea
   ↓
Focused product interview
   ↓
MVP boundary + non-goals
   ↓
Approved technical direction
   ↓
Claude/Codex operating model
   ↓
Harness + durable project briefs
   ↓
Optional first bootstrap spec
   ↓
You explicitly start implementation
```

A Greenfield setup can generate:

```text
project/
├── README.md                         # optional product-facing introduction
├── AGENTS.md                         # shared engineering contract
├── CLAUDE.md                         # Claude orchestration policy
├── .claude/
│   ├── agents/
│   ├── rules/
│   └── skills/
├── .ai/
│   ├── project/
│   │   ├── brief.md                  # problem, users, outcome, MVP scope
│   │   ├── architecture.md           # planned stack and constraints
│   │   ├── roadmap.md                # initial milestones
│   │   └── open-questions.md         # blocking vs non-blocking decisions
│   ├── backlog.md
│   ├── decisions/
│   ├── reports/
│   ├── specs/
│   │   └── current-task.md           # ready-to-build mode only
│   ├── runs/
│   └── harness/project-profile.json
└── docs/ai-harness/README.md
```

The setup command does **not** run `git init`, install dependencies, scaffold the product, call Codex, commit, push, or deploy. You review the context and first contract before implementation begins.

## Existing-project mode: repository evidence → operating model

For an established project, the flow becomes:

```text
Repository evidence
        ↓
Focused read-only research
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

The inspector detects, where available:

- languages, frameworks, package manager, and repository shape,
- real test, lint, typecheck, and build commands,
- existing `README.md`, `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`, and `.ai/`,
- Git state and project boundaries,
- local Claude Code and Codex capabilities,
- secret-bearing filenames without opening their contents.

Repository content is evidence—not an instruction source that can override the plugin.

## Three harness tiers

| Tier | Best for | What it adds |
|---|---|---|
| **Lite** | experiments, small prototypes, weak or incomplete gates | shared contracts, orchestration, selected implementation path, `.ai/` knowledge structure |
| **Standard** | serious MVPs and production products | focused researcher, independent reviewer, stronger specification and verification flow |
| **Fleet** | established projects with repeated, genuinely independent parallel work | lane contracts, ownership boundaries, ledger, Git worktrees, bounded Codex lanes |

Greenfield projects start at Lite or Standard. **They never start at Fleet.** Fleet requires a proven baseline, reliable gates, clean ownership, and real parallel-work evidence.

A typo or obvious one-file edit also bypasses the full ceremony. Complexity should be proportional to the task.

## Clear role separation

| Role | Owns | Does not own | Produces |
|---|---|---|---|
| **Main Claude** | product judgment, architecture, synthesis, specifications, integration, final gate | noisy bulk exploration | decisions, specs, verified result |
| **Researcher** | repository evidence and existing patterns | implementation or final product decisions | concise report |
| **Implementation delegate** | scoped execution against an accepted contract | unresolved product ambiguity | diff and check results |
| **Reviewer** | independent comparison of spec, diff, and behavior | feature implementation | verdict and findings |

The execution agent does not need the entire conversation. It receives a self-contained contract with the goal, context, scope, constraints, acceptance criteria, and exact verification commands.

## Codex is optional

Development Harness supports three implementation transports:

- **Official Codex plugin** — delegate through OpenAI's Claude Code integration.
- **Direct Codex CLI** — run a local `codex exec` process against an on-disk spec.
- **Claude-only** — keep the same contract and verification discipline without Codex.

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

```text
/development-harness:audit
```

The read-only audit checks for:

- duplicated or conflicting instructions,
- overloaded always-on context,
- vague delegation contracts,
- researchers with unnecessary write access,
- missing verification gates,
- stale or noisy project memory,
- unnecessary fleet complexity,
- hard-coded model assumptions,
- unsafe Git, network, secret, or automation boundaries.

It reports findings without modifying the project.

## Safe by default

- no secret-value reads,
- no network access by default,
- no permission or sandbox bypasses,
- no active hooks,
- no dependency installation or application scaffolding,
- no automatic Git initialization, commit, push, pull request, deploy, or migration,
- no silent overwrite of existing project instructions,
- staging outside the target project,
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
- Git recommended; required for Fleet/worktrees
- Codex optional

No Python package installation is required.

## Core principles

1. **Understand intent before architecture.** A Greenfield project starts with problem, users, outcome, and scope—not arbitrary folders.
2. **Distinguish plans from evidence.** Planned commands and paths are not real until the repository proves them.
3. **Inspect before asking.** Existing-project users should not repeat facts already present in the repository.
4. **Persist durable knowledge.** Briefs, reports, decisions, specs, and backlog live with the project—not only in chat history.
5. **Specify before delegating.** Execution quality is bounded by contract quality.
6. **Verify independently.** A delegate's completion message is a claim, not evidence.
7. **Use the smallest sufficient system.** More agents and more files are not automatically better.
8. **Preserve operator control.** High-impact actions remain explicit.

## Documentation

- [Architecture](docs/architecture.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Publishing and releases](docs/publishing.md)
- [Acknowledgments](ACKNOWLEDGMENTS.md)
- [Changelog](CHANGELOG.md)

## License

MIT

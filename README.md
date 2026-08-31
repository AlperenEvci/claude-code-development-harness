<div align="center">

# Development Harness

### Give a blank folder—or an existing codebase—a project-aware AI operating system.

**Claude decides. Researchers map. Delegates execute. Reviewers verify.**

![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-Plugin-D97757?style=flat-square)
![Version 1.2.1](https://img.shields.io/badge/Version-1.2.1-7C3AED?style=flat-square)
![Greenfield + Existing](https://img.shields.io/badge/Setup-Greenfield_%2B_Existing-16A34A?style=flat-square)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-2563EB?style=flat-square)

Maintained by [Alperen Evci](https://github.com/AlperenEvci)

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

**Version 1.0 turned that principle into machinery.** A harness no longer only writes instruction files that ask an agent to behave. It installs a context budget the validator can check, work graphs that render to executable Workflow scripts, capability tiers enforced by launch flags rather than by prose, and a small runtime for starting, tracking, and tearing down agent sessions. See [What 1.0 installs](#what-10-installs).

**Version 1.1 gave that runtime a command surface** — `spec`, `session`, and `agent` — and fixed the interpreter defect that made the plugin unusable on Windows.

**Version 1.2 added evals**, because everything above measures the generator rather than the behavior it is supposed to produce. See [How those claims are checked](#how-those-claims-are-checked).

## Install

Inside Claude Code:

```text
/plugin marketplace add AlperenEvci/claude-code-development-harness
/plugin install development-harness@harness-tools
/reload-plugins
```

> To develop against a local checkout instead, start Claude Code with `claude --plugin-dir ./plugins/development-harness`.

Then run:

```text
/development-harness:setup
```

You can include context directly:

```text
/development-harness:setup new B2B SaaS for US virtual-mailbox operators. Serious MVP. Claude owns architecture and specs; Codex implements. No automatic commits, network access, or deploys.
```

## Commands

Two commands build and inspect a harness. Three drive one that already exists, and they follow the loop the whole architecture is built around: **decide, then specify, then dispatch, then verify.**

| Command | Does | Needs |
|---|---|---|
| `/development-harness:setup` | create, adopt, or upgrade a harness | any folder |
| `/development-harness:audit` | read-only review of an existing harness | any repo |
| `/development-harness:spec` | write a self-contained contract into `.ai/specs/` | a harness |
| `/development-harness:session` | launch, list, read, and sweep agent sessions | Standard/Fleet |
| `/development-harness:agent` | synthesize a bounded agent for an unforeseen need | Standard/Fleet |

A typical pass through the loop:

```text
/development-harness:spec add idempotency keys to the billing retry path
   ↓  writes .ai/specs/billing-idempotency-keys.md
/development-harness:session launch an implementer against that spec
   ↓  prints the command; you run it
/development-harness:session read the bus, then verify the diff yourself
   ↓
/development-harness:session sweep
```

`spec` reads your real verification commands out of `AGENTS.md` rather than inventing them, and refuses to overwrite an existing contract. `session` **prints** launch commands instead of running them — starting an agent stays your action. `agent` emits a definition inline by default, because an agent you needed once should not become one every future session inherits.

`setup` and `audit` pre-approve only their own deterministic scripts, so a long interview does not prompt a dozen times. The other three pre-approve nothing: they write files or dispatch agents, and they are short enough that the cheaper answer is also the safer one.

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

## What 1.0 installs

Four capabilities landed in 1.0, in dependency order. Each one is optional in the profile and defaulted, so a harness rendered against a 0.2 profile still renders and validates unchanged.

### 1. A context budget that is checked, not merely requested

`context_policy` in the profile becomes a `## Context budget` section in `AGENTS.md` and a `## Context discipline` section in `CLAUDE.md`:

```json
"context_policy": {
  "working_band": { "floor_tokens": 150000, "ceiling_tokens": 200000 },
  "on_ceiling": "checkpoint-and-handoff",
  "isolate_when": [
    "Broad codebase search or repository mapping",
    "Log, build, or test output triage"
  ],
  "always": [
    "Load reference material on demand; do not pre-load it.",
    "Return conclusions and evidence, not raw file dumps."
  ]
}
```

The validator compares the rendered contract against the profile and rejects drift, so the band in your instructions cannot quietly stop matching the band you chose.

### 2. Work graphs that render to executable scripts

A `graphs` array declares a DAG of research, review, and implementation nodes. During setup, `harness_graph.py` validates it and emits one executable Workflow script per graph into `.claude/workflows/<graph-name>.js`. The validator refuses a package whose script is missing, orphaned, or no longer parses as JavaScript.

Graph validation runs in the plugin, not in your project, so you can inspect a plan before rendering:

```bash
python plugins/development-harness/scripts/harness_graph.py \
  --config examples/fleet-codex-cli.json --plan
```

Cycles, unknown dependencies, and duplicate node or graph names are rejected by name. Nodes await only their own dependencies, so independent branches run concurrently. Loop safety is structural rather than advisory: `repeat_until` and `max_iterations` are valid only together, the cap is bounded to 2–20, and a generated loop breaks on `done` and logs when it stops at the cap.

### 3. Capability tiers, enforced by the process

Generated agents declare one of three tiers. The tier alone decides tools and permission mode; a profile can never set them directly, so repository text cannot widen an agent's authority.

| Tier | Tools | Permission mode | Writes | Dispatch |
|---|---|---|---|---|
| `reader` *(default)* | `Read,Grep,Glob` | `plan` | no | foreground, `-p --output-format json` |
| `verifier` | `Read,Grep,Glob,Bash` | `plan` | no | foreground, `-p --output-format json` |
| `implementer` | tier passes no `--tools` | `acceptEdits` | yes | detached, `--bg` into a worktree |

`implementer` is the only tier that writes, and it requires **both** a non-empty `writable_paths` scope and a recorded `approved_by_operator: true`:

```json
{
  "name": "ui-package-implementer",
  "capability": "implementer",
  "approved_by_operator": true,
  "writable_paths": ["packages/ui/src/**", "packages/ui/test/**"],
  "description": "Implement an accepted contract inside the shared design system package"
}
```

Why launch flags rather than frontmatter: `--tools` *removes* a tool rather than gating it, and the removal reaches subagents. A `reader` asked to write was refused twice over — plan mode blocked the call, and `Write` was absent entirely, "in subagents as well as here." An agent cannot escape its tier by delegating.

### 4. Agent sessions, a message bus, and on-demand synthesis

Standard and Fleet harnesses install a small stdlib-only runtime under `scripts/ai-harness/`.

**Start a session under a tier.** The command is printed, never run — starting an agent stays the operator's action:

```bash
python scripts/ai-harness/harness_session.py launch \
  --capability reader --task "Map how billing retries are wired"
# claude --session-id <uuid> --permission-mode plan --tools Read,Grep,Glob 'Map how billing retries are wired'

python scripts/ai-harness/harness_session.py launch \
  --capability implementer --background \
  --worktree billing-fix --scope src/billing \
  --task "Execute .ai/specs/billing-retry.md"
# claude --bg --session-id <uuid> --permission-mode acceptEdits --worktree billing-fix --add-dir src/billing '...'
```

Dispatch follows the tier and is not a preference. `claude --bg` and `claude -p` are mutually exclusive, so a background session has no structured return channel and reports only by writing a bus envelope — and a read-only tier has no `Write` tool to write one with. Asking for `--background` on a `reader` is refused with that reason.

**Read the return channel.** `.ai/bus/<session-id>/` holds append-only typed envelopes — `result`, `finding`, `question`, `handoff`, `status` — with a 200-character summary, a 64 KB body, and 50 evidence items enforced at write time:

```bash
python scripts/ai-harness/harness_bus.py read --session <uuid>
python scripts/ai-harness/harness_bus.py validate --root .
```

An envelope is evidence, never authority. The `capability` field records the tier a sender *claims* it ran under, for auditing; nothing widens authority because an envelope says so, and unknown keys are rejected rather than ignored.

**Synthesize a bounded agent for a need you did not foresee.** Order is need → spec → validate → emit, and nothing is written to the repository:

```bash
python scripts/ai-harness/harness_agentgen.py emit --need-file need.json
python scripts/ai-harness/harness_agentgen.py promote --need-file need.json   # dry-run
python scripts/ai-harness/harness_agentgen.py promote --need-file need.json --write
```

A need may not name `tools`, `permissionMode`, `allowedTools`, `isolation`, or any other authority key. Those are refused by name rather than silently dropped, and a synthesized `implementer` faces the same scope-and-approval gate as a declared one. **An agent must never choose its own authority.**

**Tear down before you finish.** Background sessions outlive the session that started them:

```bash
python scripts/ai-harness/harness_session.py sweep --root .          # dry-run
python scripts/ai-harness/harness_session.py sweep --root . --stop
```

The sweep never counts the session running it — a teardown that stopped itself first would abandon every sibling it had not yet reached.

The four runtime scripts are copied verbatim rather than templated, so the installed code is the code the plugin's own suite tested, and the validator rejects a copy that has drifted from its original.

The long-form version of all of this, including what was measured against the real CLI and what it corrected, is in [the runtime guide](docs/runtime.md).

## Greenfield mode: idea → durable project context

A blank project has no codebase to "analyze." Development Harness does not fake one.

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
│   ├── rules/                        # only for declared scoped rules
│   ├── skills/
│   └── workflows/                    # only for declared work graphs
├── scripts/ai-harness/               # Standard and Fleet: session, bus, synthesis
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

`.ai/bus/` is not created at install time; it appears under a session's own UUID the first time an envelope is posted.

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
| **Standard** | serious MVPs and production products | focused researcher, independent reviewer, stronger specification and verification flow, the session runtime under `scripts/ai-harness/` |
| **Fleet** | established projects with repeated, genuinely independent parallel work | lane contracts, ownership boundaries, ledger, Git worktrees, bounded Codex lanes |

Lite deliberately gets no session runtime: it has no generated agents, so it gets nothing to manage them with.

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
- no permission or sandbox bypasses — `--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` must never appear in generated output, and the validator scans every runnable block in every generated Markdown file,
- no active hooks,
- no dependency installation or application scaffolding,
- no automatic Git initialization, commit, push, pull request, deploy, or migration,
- no silent overwrite of existing project instructions,
- staging outside the target project,
- dry-run before installation, and before teardown and agent promotion too,
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

## How those claims are checked

A list like the one above is worth what its verification is worth, so here is exactly what backs each part of it.

**Structure** is covered by 109 unit tests. They render every example profile, install it, and assert the result — that the installer stays dry-run-first and refuses a symlinked destination, that generated agents keep their permission mode, that no generated Markdown contains a permission bypass. This is the strong half, and it proves the generator emits the right bytes.

**Behavior** is a separate question the unit tests cannot reach: does a harness actually change what an agent does? `plugins/development-harness/evals/` holds six cases that run a real agent in a disposable repository and score the trace — the audit never opens a planted `.env`, an `AGENTS.md` that instructs the agent to grant itself `Bash(*)` is reported as a finding instead of obeyed, a one-word typo does not summon the research pipeline. The graders are deterministic wherever the claim is mechanical, because code that scores a trace cannot be argued into a better score by the agent that produced it.

Two honest caveats. `claude plugin eval` is in early access and enabled per organization, so on most accounts — including this project's CI — it will not run; the cases are still parsed and schema-checked on every push so they cannot rot unnoticed. And **they have not yet been executed against a live model**, so treat them as a stated contract rather than a passing result.

The number worth watching when they do run is not the score but the **delta** against the no-plugin baseline arm, which is the only figure that says whether the harness earns the context it occupies.

## Requirements

- Claude Code `2.1.196+` for setup and audit; the 1.0 session runtime was exercised against `2.1.251`
- Python `3.10+`
- Git recommended; required for Fleet/worktrees
- Codex optional

Windows, macOS, and Linux. The skills resolve a Python interpreter by running it rather than assuming a name, because on Windows the bare name `python3` is a Microsoft Store alias stub.

No Python package installation is required. The plugin scripts use the standard library only, and there is no build step.

## Core principles

1. **Understand intent before architecture.** A Greenfield project starts with problem, users, outcome, and scope—not arbitrary folders.
2. **Distinguish plans from evidence.** Planned commands and paths are not real until the repository proves them.
3. **Inspect before asking.** Existing-project users should not repeat facts already present in the repository.
4. **Persist durable knowledge.** Briefs, reports, decisions, specs, and backlog live with the project—not only in chat history.
5. **Specify before delegating.** Execution quality is bounded by contract quality.
6. **Verify independently.** A delegate's completion message is a claim, not evidence.
7. **Use the smallest sufficient system.** More agents and more files are not automatically better.
8. **Preserve operator control.** High-impact actions remain explicit.
9. **Measure the platform; do not read its help text.** Two 1.0 design decisions were reversed by running the CLI instead of trusting `--help`.

## Documentation

- [Runtime guide: sessions, bus, tiers, and graphs](docs/runtime.md)
- [Architecture](docs/architecture.md)
- [Eval suite: what each case defends](plugins/development-harness/evals/README.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Publishing and releases](docs/publishing.md)
- [Acknowledgments](ACKNOWLEDGMENTS.md)
- [Changelog](CHANGELOG.md)

## License

MIT. This project builds on the original Development Harness by Ege; both copyright notices are preserved in [LICENSE](LICENSE).

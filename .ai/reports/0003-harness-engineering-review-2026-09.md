# Research Report: the harness against September 2026 harness-engineering practice

Date: 2026-09-06
Status: proposed
Supersedes the gap list in `0002-external-practice-review.md` (2026-08-31), whose five
gaps closed across 1.2.0 through 1.6.0. This report re-benchmarks 1.12.0 against what
was published since, across seven dimensions: routing, context management, loop
engineering, hooks, delegation, cost, and evaluation.

Method: one read-only pass over the plugin and its generated output (file:line evidence
in the working notes), and three web sweeps over primary sources fetched on 2026-09-06.
Only fetched sources are cited. Claude Code docs pages carry no date; they reference
versions up to v2.1.260 and are treated as current.

## Verdict in one paragraph

The harness is still strongest where the field is weakest: authority is enforced at the
process (tier table, launch flags, two-key implementer gate, untrusted-text rule), and
every prose-to-mechanism move the last review asked for has shipped. What has changed
is the baseline. Anthropic's 2026 guidance now states flatly that an instruction in
`CLAUDE.md` is a request and a `PreToolUse` hook is enforcement, and the generated
harness ships **no hook of any kind**. Every guarantee in routing, context, and loop
engineering therefore rests on the model choosing to run a command. That is now the
single largest gap, and it is a product decision rather than a code defect: the plugin
chose `hooks_policy: disabled | examples-only` for a security reason that does not
actually apply to hooks the plugin authors itself.

## Where it stands, per dimension

| Dimension | Mechanism today | Prose only | Field position (2026) |
|---|---|---|---|
| Routing | tier table, launch-flag enforcement, validator tier check | Direct/Standard/Complex working model | aligned: "skip the plan if the diff fits in one sentence" is the docs' own rule |
| Context | `harness_checkpoint.py` (exit 3 at ceiling), `--brief`, band-drift validator | keep the band, isolate_when | behind: no `PreCompact`, no `SessionStart[compact]`, band is static while auto-compact is native and model-dependent |
| Loop | JSON ledger with evidence-gated `passes`, correlation id, `launch --report` | session-start checklist, one task per session | behind: nothing fires at start, no smoke test, no Stop gate |
| Hooks | renderer rejects `hooks` on agents; policy validated | "do not activate hooks" | behind: consensus stack is PreToolUse guard, PostToolUse format, Stop verify, SessionStart re-inject, PreCompact checkpoint |
| Delegation | frontmatter from tier table, bus caps, implementer gate, agentgen | orchestration pipeline, Codex transport | aligned, with two small holes (below) |
| Cost | `trace.duration_ms`, `trace.tokens` from launcher; per-unit aggregation | "escalation costs a round trip" | behind: no model or effort per role, no cost, no cache fields, defaults `inherit` |
| Evals | 7 cases, schema-checked on push; report, graph, audit, check_installed | rubric | unchanged: never executed; runner still early access |

## Gap 1 - No hooks. Every guarantee is model discipline.

The 2026 sources are unanimous, and several are Anthropic's own:

- Best practices: hooks are for "actions that must happen every time with zero
  exceptions"; convert reliably-followed `CLAUDE.md` rules into hooks. The verification
  ladder is in-prompt check, then `/goal`, then a deterministic Stop hook, then a
  fresh-context verifier.
- Hooks guide: `PreToolUse` fires before the permission check in every mode including
  `bypassPermissions`; a hook `deny` cannot be loosened by mode; the most restrictive
  decision wins across hooks.
- Feature matrix: "An instruction like 'never edit .env' in CLAUDE.md is a request; a
  PreToolUse hook is enforcement."
- Anthropic's own security-guidance plugin ships a five-hook stack, and delegates hard
  enforcement to a `PreToolUse` block.

Against that, the generated harness carries as prose: never read `.env` or
`settings.local.json`, never run destructive git, never commit, run `--brief` on
resume, write a checkpoint at the ceiling, keep the ledger honest. Each is exactly the
kind of rule the docs say to move into a hook. The 1.12.0 changelog already names the
failure mode: "a checklist of three is three chances to skip one."

Why the original exclusion does not bind here. The plugin refuses hooks because
repository text in a scanned project is untrusted and must never be promoted into
privileged configuration. That rule is right and should stay. But a hook the renderer
emits from its own template, shown in the dry run, installed under the same
no-silent-overwrite rules as every other file, is not scanned text. It is the plugin's
own authored output, the same trust class as the tier table. The security argument
protects against *adopting* hooks from a target repository, not against *generating*
them.

Recommended shape, as a third `hooks_policy` value (`guarded`), rendered into
`.claude/settings.json` in the payload and refused if the target already has one:

| Event | Matcher | Action | Source |
|---|---|---|---|
| `PreToolUse` | `Edit\|Write\|Read` | deny on secret-bearing and protected paths | hooks guide, security plugin |
| `PreToolUse` | `Bash`, `if: "Bash(git *)"` | deny `git commit/push/reset --hard/clean`, `rm -rf` on critical paths | hooks guide, permission-modes |
| `PreToolUse` | `Bash` test commands | `updatedInput` rewrite to failures-only output | costs page (tens of thousands of tokens to hundreds) |
| `SessionStart` | `startup\|resume\|compact` | run `harness_report.py --brief`; stdout enters context | hooks guide, context-window page |
| `PreCompact` | `auto\|manual` | run `harness_checkpoint.py write` with intent from `last_assistant_message` | hooks reference |
| `Stop` | - | run the profile's smallest check only when the tree changed; honor `stop_hook_active`; expect the 8-block cap | best practices, hooks guide |

Windows parity requires the exec form (`args: []`) and `python`, not `python3`, which
the gate already learned once. Every hook must be non-model (`command` type); `prompt`
and `agent` hooks add latency and the latter is experimental.

Two documented downsides to design around: `Stop` fires on every response end, so the
gate must be cheap and conditional; and parallel `updatedInput` hooks race, so the test
filter must be the only rewriter of `Bash` input.

## Gap 2 - The context policy predates native compaction

The band (150k-200k, exit 3 at the ceiling) was the right answer when nothing else
existed. The platform has moved:

- Auto-compact is native, configurable 100K-1M (`/autocompact`, `--autocompact`,
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW`), and model-dependent: Sonnet 5 is 1M native.
  Claude 4.7+ tokenizers produce roughly 30% more tokens for the same text. A static
  150k-200k band is therefore wrong for some models in both directions.
- What survives compaction is specified: root `CLAUDE.md` and unscoped rules are
  re-injected from disk; **hook-added context is summarized away**; invoked skill bodies
  are re-injected capped at 5,000 tokens per skill and 25,000 total; the top of a
  `SKILL.md` is what survives truncation.
- Anthropic's own harness post (2026-03) removed per-sprint context resets between
  Opus 4.5 and 4.6 and drew the lesson: every harness component encodes an assumption
  about model weakness; remove them one at a time and measure.
- Two 2026 papers agree on the mitigation for context rot: an external obligation
  checklist handed to the verifier (10/10 vs 5/10 for generic self-validation), and
  length-triggered summarization or subagent isolation. Neither is a fixed threshold.

The caller-reported `--used` figure is honest about its limit and remains useful as a
fallback, but the primary mechanism should be event-driven: `PreCompact` writes the
handoff, `SessionStart[compact]` reads it back. That closes the half the last review
called impossible from outside the harness. The band should be derived from the model
in the profile rather than fixed.

Also in scope: path-scoped `.claude/rules/*.md` with `paths:` frontmatter now exist and
load only when a matching file is read. The generated `AGENTS.md` important-paths and
sensitive-areas content is a natural fit and would leave the root file.

## Gap 3 - The generated CLAUDE.md is over the line

The docs' target is under 200 lines per file, and Anthropic's July 2026 post on Claude 5
generation models reports cutting over 80% of Claude Code's own system prompt with no
measurable eval loss: delete rigid rules, repeated tool instructions, and facts
inferable from the filesystem; keep purpose and gotchas. `@imports` load at launch, so
they do not save anything.

The Standard-tier `CLAUDE.md` renders to roughly 180-210 lines before its `@AGENTS.md`
import adds the context-budget section and the rest. The agent-sessions section alone
is about 80 lines of procedure, which the docs say belongs in a skill. Rendered size
should be measured by the validator, not inferred, and the sessions procedure should
move into the existing `session` skill body.

## Gap 4 - Cost is measured in tokens and decided nowhere

What the field now expects a run record to carry, and where the harness stands:

| Field | Available from | Envelope v2 |
|---|---|---|
| duration, input, output tokens | `-p --output-format json` | yes |
| `total_cost_usd`, `costBasis` | same result record | no |
| model, effort per entry (`modelUsage`) | same; `usage` excludes subagents | no |
| cache read / cache creation tokens | same | no |
| `num_turns`, `subtype` (success, `error_max_budget_usd`) | same | no |

The launcher already parses this JSON. Adding the fields is a version-3 envelope and a
`--cost` reader, not new infrastructure. Cache hit ratio is the metric Anthropic treats
"like uptime" (cache reads are 0.1x input; 0.025x on Fable 5.1), and the harness's own
launch shape works against it: each `-p` lane is a fresh prefix, and cache scope is per
machine and directory, so worktree lanes never share. `subagentPromptCacheTtl` and
`promptCacheTtl` are the documented levers.

Model and effort per role. Both generated agents default to `inherit`, which silently
runs research and review on the parent's model. The docs recommend `model: haiku` for
simple subagents and Sonnet for teammates; the built-in Explore inherits up to Opus
unless overridden. The subagent frontmatter now also carries `effort`, and Anthropic's
cost-optimization page says to sweep effort on the current model before tiering models,
since multi-model setups "frequently lose to the baseline model at lower effort." So:
explicit `model` and `effort` per tier in the profile, defaults `haiku`/`low` for
readers that only search, `sonnet`/`medium` for research and review, and the eval suite
as the thing that approves a step down.

Budget caps. `--max-budget-usd` now counts subagent spend and fails further spawns
(v2.1.217+), but remains print-only; the backlog item on background lanes stands.
`--max-turns` and frontmatter `maxTurns` are the bound that does exist for both, and
`maxTurns` is already rendered.

## Gap 5 - The evals still have never run, and a forward-compat risk is sitting in launch

Unchanged since the last review: seven cases, schema-checked, zero scored runs. The
runner is still early access, and no official documentation page for it could be
located; what is known comes from a September 2026 secondary write-up: free graders
(`regex`, `tool_used`, `tool_order`, `file_exists`), an ablation arm that is the only
documented way to catch a skill that never triggers, `--max-cost-usd` for CI. The
recommendation is procedural: request access, and gate CI with a cost cap when it
lands. `claude plugin validate --strict` is GA and should be in the gate now.

The forward-compat risk. The CLI reference says `--bare` skips hooks, skills, agents,
plugins, MCP, and `CLAUDE.md`, and "will become the default for `-p`". Every read-only
tier launches with `-p` and depends on `CLAUDE.md` and the agent definitions being
loaded. When that default flips, a `reader` lane comes up without its contract.
`launch_argv` should pin the opposite explicitly, and a test should assert it.

## Smaller holes in delegation

- Researchers can spawn writers. `tools: Agent(researcher)` restricts which subagent
  types an agent may spawn; readers should carry it.
- Parent `bypassPermissions` or `acceptEdits` overrides a subagent's `permissionMode`,
  so tier enforcement through the tools list is the right design and the validator's
  whole-list comparison is the right check. Worth stating in the runtime guide so
  nobody weakens it thinking the mode is the guard.
- The generated `harness-orchestration` skill lacks `disable-model-invocation`, unlike
  the plugin's own skills.
- Plugin agents have the lowest precedence; a project `.claude/agents/` file with the
  same name shadows a generated one. `check_installed.py` could report the shadow.
- Agent teams are experimental, cost about 7x in plan mode, and turn any named subagent
  into a teammate when enabled. Keep them off; the harness's graph-emitted workflows are
  the sanctioned path, and `workflowSizeGuideline: small` bounds them.

## Where the harness is ahead, and should stay

- Authority at the process, not the prompt. Nothing reviewed does this better.
- Evidence-gated ledger that refuses a pass without an exit code, and refuses to run
  its own verify string. Both papers on context rot say the external checklist is the
  mitigation; the spec-plus-reviewer path already hands one over.
- Bounded loops in emitted workflows (2-20 iterations, break on done) match the
  ralph-loop guidance without a Stop-hook re-feed.
- Envelope trace fields are set by the launcher and absent from the agent-facing
  schema, because a self-reported token count is a guess. The cost fields above should
  follow the same rule.

## Recommended order

1. **`hooks_policy: guarded`.** Rendered, dry-run, refused over an existing
   `settings.json`, exec-form, command hooks only. Start with the `PreToolUse` guards
   and `SessionStart` brief; add `PreCompact` and `Stop` once the first two are in the
   gate. This is the one change that alters what the product is.
2. **Compaction-native context policy.** `PreCompact` checkpoint, `SessionStart[compact]`
   resume, band derived from the model, `--used` demoted to fallback.
3. **Shrink the generated `CLAUDE.md`.** Validator measures rendered line count; the
   sessions procedure moves into the `session` skill; sensitive paths move into
   path-scoped rules.
4. **Model and effort per tier.** Profile fields with explicit defaults; `inherit` stops
   being the default for readers.
5. **Envelope v3 and a `--cost` reader.** Cost, model, effort, cache fields, turns, exit
   subtype, from the JSON the launcher already parses.
6. **Pin `-p` against `--bare`,** and add `claude plugin validate --strict` to the gate.
7. **Run the evals** when access arrives, with `--max-cost-usd` in CI.

1 and 2 change the product; 3 through 6 are each a bounded change with a test. The
first two touch the renderer, validator, templates, tests, references, and the
changelog together, per the engineering rules.

## Where sources disagree

- Parallel writers: Cognition (2025) says never; Anthropic's C-compiler run (2026-02)
  did it with 16 agents behind file locks and git merges. Reconcile as: parallel only
  for decomposable, test-verified work. The harness's worktree-per-lane model already
  fits that reading.
- Rules versus judgment: the Claude 5 post argues for stripping prose rules; the docs
  still say anything that must be deterministic goes in a hook. Not a contradiction:
  fewer prose rules, more hooks, which is the direction of gaps 1 and 3 together.
- Thresholds: the 85% / 20K / 10% figures are LangChain Deep Agents defaults, not
  Claude Code's. No Anthropic source gives a compact-at-X% number.

## Not verified

- An official `claude plugin eval` documentation page (404 at every guessed path).
- Claims of an "auto model" default in Claude Code; search results conflate it with
  `--permission-mode auto`.
- Cursor, Devin, Factory, and Amp primary guidance (not fetched).
- Rendered `CLAUDE.md` line counts above are inferred from templates, not measured.

## Sources

Anthropic engineering and docs: Effective harnesses for long-running agents (2025-11);
Effective context engineering (2025-09); Harness design for long-running application
development (2026-03); Building a C compiler with a team of parallel Claudes (2026-02);
The new rules of context engineering for Claude 5 generation models (2026-07);
Demystifying evals for AI agents (2026-01); Lessons from building Claude Code: prompt
caching is everything; Steering Claude Code (2026-06); Claude Code docs for hooks,
hooks guide, sub-agents, plugins reference, agent teams, workflows, best practices,
features overview, permission modes, costs, prompt caching, memory, context window,
model config, checkpointing, goal, headless, CLI reference, monitoring usage, Agent SDK
cost tracking, security guidance; Claude Platform docs for pricing, effort, task
budgets, context editing, optimizing for cost and intelligence, choosing a model.
Others: LangChain Deep Agents context management (2026-01); Cognition, Don't build
multi-agents (2025-06); Manus context-engineering lessons (2025-07); Google Developers,
Driving the agent quality flywheel (2026-06); Langfuse agent evaluation (2026-07);
Braintrust agent observability guide (2026-06); OpenAI codex AGENTS.md; Codex and
Gemini CLI hooks references; arXiv 2607.17937, 2606.29718, 2606.23525; obra/superpowers;
mattpocock/skills; anthropics/claude-code issue #26179 and the ralph-wiggum plugin
README. Secondary: matthewswong.com on plugin eval; paddo.dev on Boris Cherny's setup;
pixelmojo hook patterns; mindstudio on subagent cost.

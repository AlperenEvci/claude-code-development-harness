# Research Report: what the field does that this harness does not

Date: 2026-08-31
Status: accepted

## Question

The harness is engineered well by its own measures — 99 tests, 82% line coverage, zero
dependencies, both CI legs green. That measures the generator, not the thing it
generates. Does the *generated harness* reflect what the people who build agents for a
living have published, and where does it fall short?

Sources reviewed: Anthropic engineering (long-running harnesses, context engineering,
writing tools for agents), Google Developers/DeepMind (the agent quality flywheel),
OpenAI (agentic governance and guardrails), LangChain (context engineering, Deep
Agents), Matt Pocock's AI coding workflow, and a six-layer reference architecture for
agentic software engineering (arXiv 2604.26275).

## Where the harness already stands up

Benchmarked against the six-layer reference architecture:

| Layer | Harness position |
|---|---|
| L0 foundation model | delegated to Claude Code, deliberately |
| L1 reasoning, memory, self-reflection | **partial** — `.ai/` is durable memory; no self-critique loop beyond the reviewer agent, and no compaction |
| L2 agent–computer interface | delegated, correctly |
| L3 tools and environment | covered — worktrees, gates, real project commands |
| L4 orchestration | **strong** — tiers, graphs, sessions, bus |
| L5 governance and safety | **strongest** — tier enforcement at the process, two-key implementer gate, untrusted-text rule |

The paper calls L5 "currently the least mature layer" and "rapidly becoming the
bottleneck on enterprise deployment." The harness is strongest exactly where the field
is weakest. That is the differentiator, and it is worth naming as the product thesis
rather than treating tiers as an implementation detail.

Independent convergence worth noting: the four-strategy frame LangChain uses — write,
select, compress, isolate — maps almost exactly onto what the harness already does.
`.ai/` is *write*, on-demand references are *select*, the bus caps are *compress*, and
capability-tiered sessions are *isolate*. The design was not derived from that frame,
which is mild evidence the shape is right.

## Gap 1 — There are no evals. This is the largest gap by a wide margin.

Every source converges here, and the harness has nothing:

- Anthropic's tool-writing guidance is built on an evaluation-driven loop: prototype,
  build realistic tasks needing several tool calls, measure accuracy, runtime, token
  consumption, and tool errors, then improve from transcripts.
- Google's **agent quality flywheel** is five stages — prepare data, run inference,
  grade, analyze failures, optimize — with one architectural rule stated flatly:
  *whatever proposes a fix never grades it.* Optimizer and evaluator stay decoupled, or
  the optimizer games the metric.
- OpenAI measures guardrails with precision and recall over a labelled JSONL set that
  deliberately includes adversarial and legitimate cases.

The harness's 99 tests assert that the *renderer* emits the right bytes. Nothing
asserts that a generated harness produces better agent behavior, and nothing would
catch a regression in the thing the product actually sells. The Windows defect proved
the shape of this hole: the Python was covered, and the part a user runs was not.

`claude plugin eval` exists and is unused.

Google's second rule is as important: trust **deltas** between runs, not absolute
scores. An eval suite whose absolute number is meaningless is still valuable.

## Gap 2 — The context policy is a declaration with no mechanism

`context_policy.on_ceiling: "checkpoint-and-handoff"` is validated against the rendered
Markdown and nothing else. Nothing measures the band, nothing acts at the ceiling. The
validator confirms the *documentation* matches the *profile* — two descriptions of an
intention, neither of which is a mechanism.

Compare Deep Agents, which implements both halves:

- tool inputs or results over **20,000 tokens** are offloaded to the filesystem and
  replaced by a reference plus a ten-line preview,
- at **85% of the context window** a summarization step writes a structured summary —
  session intent, artifacts, next steps — and the original transcript is persisted as
  the canonical record.

Anthropic's compaction guidance adds the ordering: maximize recall of architectural
decisions and unresolved bugs first, *then* trim; and the safest single lever is
clearing stale tool results rather than summarizing prose.

The harness has the right file locations for this already (`.ai/runs/`, the bus). It
has no code that writes a checkpoint.

## Gap 3 — Progress is Markdown prose, not a machine-checked ledger

Anthropic's long-running-harness article is the closest published work to this project,
and it prescribes a specific, testable shape:

- a **feature list in JSON** as ground truth, every item `passes: false` until proven,
- `claude-progress.txt` updated every session,
- a git commit per session as a checkpoint to roll back to,
- a mandatory session-start checklist: `pwd`, read git log and progress, pick the next
  unfinished item, start the environment, run a smoke test to detect inherited breakage,
- one feature per session, enforced.

And one detail worth taking literally: **JSON over Markdown**, because models are less
likely to overwrite or quietly rewrite a JSON file than a Markdown one.

`.ai/backlog.md` is Markdown prose. It is good prose — this session rewrote parts of it
— but "unfinished work" in a paragraph cannot be counted, diffed, or asserted. The
named failure modes it would prevent are exactly the ones seen in practice: an agent
declaring a project complete, and an agent leaving the tree in a broken state.

## Gap 4 — The bus is one field away from being a trace store

Google's flywheel runs on OpenTelemetry traces: production traces become the evaluation
dataset, and the same pipeline that grades development runs grades production.

The harness already has the hard part — a typed, append-only, size-capped, schema'd
channel with a sender, a capability claim, and a task reference. What it lacks is a
correlation id, a duration, and a token or cost figure. Adding those turns the bus from
a mailbox into an evidence base that an eval can consume, at very low cost.

## Gap 5 — The audit does not check the thing Pocock calls the biggest lever

Pocock's claim, from a different tradition than the labs: **the structure of the
codebase is the single biggest lever on agent output quality.** Deep modules — small
interface, rich internals — give an agent a clear surface. Shallow modules, many small
tightly-coupled files, are hard to navigate and nearly impossible to test well.

`/development-harness:audit` checks the harness. It does not check whether the
repository is *shaped* for agents. That is a differentiated feature no other harness in
this review offers, and the harness already has the inspector to build it on.

His context threshold, ~100k tokens before attention degrades, is close to the band
this repository already runs (150k–200k), and is worth reconciling rather than ignoring.

## The critique that lands

Pocock's stated position is "fix requirements first, keep skills composable, **do not
own the process**" — frameworks that own the process take away control and make bugs in
the process hard to resolve.

The harness does own quite a lot of process. `skills/setup/SKILL.md` is 304 lines of
prescribed workflow. Two defences are real: what it installs is plain files the user
owns and edits, and tiers constrain *authority* rather than *sequence*. But the defence
is not total, and "the interview is 304 lines" is a fair thing for a skeptical reader
to point at.

The honest response is not to shrink the setup skill. It is to make the generated
harness composable — small skills that compose — and to keep the opinionated part
confined to bootstrap.

## Recommended order

1. **Evals.** `claude plugin eval` over a small labelled set: does setup pick the right
   tier for a given fixture, does audit find a planted defect, does a `reader` refuse a
   write. Keep the grader separate from anything that proposes a fix.
2. **Checkpoint mechanism** — make `on_ceiling` executable. A `harness_checkpoint.py`
   that writes intent, artifacts, and next steps to `.ai/runs/`, on the Deep Agents
   shape, closing the gap between the declared policy and reality.
3. **JSON progress ledger** beside `.ai/backlog.md`, with a session-start checklist in
   the generated `CLAUDE.md`.
4. **Trace fields on the envelope** — correlation id, duration, tokens — so the bus can
   feed the eval loop.
5. **Repository-shape audit** — module depth, file fan-out, test reachability.

1 and 2 are the two that change what the product *is*. The rest are compounding.

## Sources

- Anthropic, *Effective harnesses for long-running agents*
- Anthropic, *Effective context engineering for AI agents*
- Anthropic, *Writing effective tools for AI agents*
- Google Developers, *Driving the agent quality flywheel from your coding agent*
- OpenAI, *Building governed AI agents: agentic scaffolding*
- LangChain, *Context engineering for agents*; *Deep Agents* context engineering docs
- Matt Pocock, *Workflow for AI coding* (AI Engineer 2026), via walkthrough writeups
- arXiv 2604.26275, *Agentic AI in the Software Development Lifecycle*

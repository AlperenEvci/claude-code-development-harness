# Research Report: what the other two hosts do when you launch them

Date: 2026-09-09
Status: accepted
Hosts: Codex CLI 0.153.4 (`codex exec`) and OpenCode 1.18.29 (`opencode run`), both on
Windows 11 with subscription auth. Claude Code 2.1.266 for comparison.
Fixture: a scratch git repository with a README, an `.opencode/agent/` directory
rewritten between probes, and a second scratch directory used only for the concurrency
pair.

## Question

Module 11 was designed on paper in `.ai/decisions/0005-host-portability.md` section 7:
`harness_session.py launch --host <name>` resolves the binary and maps the tier into
`codex exec --json -o -s read-only|workspace-write` and
`opencode run --format json --agent <tier-agent>`, the envelope records `host`, and
cost stays empty where the host reports none. Before writing any of it, five things had
to be measured against the installed binaries:

1. Whether those flags exist, and what the machine-readable stream actually contains -
   in particular whether it carries a session identifier the bus can correlate on, and
   whether it carries tokens or money.
2. Whether `opencode run --agent <name>` binds the named agent, and what happens when
   it cannot.
3. Whether a bound agent's permission block holds for the whole session, including
   anything it delegates to.
4. Whether the exit code is a usable success signal, or whether the launcher has to
   read the stream.
5. Whether two sessions can run at once in one directory - the concurrency rule
   decision 0005 asserted without measuring.

## Method

One non-interactive run per question. Every deny probe names a file and is checked on
disk afterwards rather than trusted to the model's summary, and each is paired with a
control that must succeed. The concurrency probes were run as two real processes
started together, once in one directory and once in two, rather than inferred from a
lock file.

| Probe | Asked | Result |
|---|---|---|
| P1 | `codex exec --json -o last.txt -s read-only` | exit 0; four event types; `-o` file holds the final message |
| P2 | what `codex exec --json` reports as cost | `turn.completed.usage` carries tokens; no money field |
| P3 | `codex exec` on a shell write under `-s read-only` | exit **0**; file absent; the denial appears only in the stream |
| P4 | `codex exec -m zzz-no-such-model` | exit 1; `item.type: error` then `turn.failed` |
| P5 | two `codex exec` together in one directory | both exit 0, distinct `thread_id`s |
| P6 | `opencode run --format json` | JSONL; `sessionID` on every event; `step_finish` carries `tokens` **and** `cost` |
| P7 | `opencode run --agent zzz_undefined_agent` | exit **0**; warning on stderr; **falls back to the default agent** |
| P8 | `opencode run --agent <a `mode: subagent` agent>` | exit **0**; same silent fallback; the write **succeeded** |
| P9 | `opencode run --agent <a `mode: primary` deny-everything agent>` | the write **still succeeded**, through the `task` tool |
| P10 | the same agent with `tools: { task: false }`, and again as `mode: all` | write refused, file absent, model reports it cannot |
| P11 | two `opencode run` together in one directory | the second dies: exit 1, `database is locked` |
| P12 | two `opencode run` together in two directories | both exit 0 |
| P13 | `opencode run -m zzz/no-such-model` | exit 1; two `type: error` events on stdout |

## Findings

**The flags decision 0005 named all exist.** `codex exec` takes `--json`,
`-o/--output-last-message`, and `-s/--sandbox` with exactly the three modes module 10
already renders. `opencode run` takes `--format json` and `--agent`. Neither has a
background flag: Claude Code's `--bg` has no counterpart on either host, so a
background launch is a Claude-only capability rather than a tier property.

**Both hosts hand back a correlation identifier, and neither hands back money.**
Codex opens with `{"type":"thread.started","thread_id":...}` and closes with
`{"type":"turn.completed","usage":{input_tokens, cached_input_tokens,
cache_write_input_tokens, output_tokens, reasoning_output_tokens}}`. OpenCode stamps
`sessionID` on every event and reports
`step_finish.part.tokens {total, input, output, reasoning, cache{write,read}}` beside
`cost`. Codex has no cost field at all. OpenCode has one, and on this subscription it
read `0` - a reported zero is not evidence that a run was free, so it must not be
copied into an envelope as though it were a measurement.

**`opencode run --agent` fails open, not closed.** An agent name that does not resolve
is a **warning on stderr and exit 0**, and the session proceeds under the default
agent. Two separate ways to not resolve were measured: a name with no file
(`agent "zzz_undefined_agent" not found. Falling back to default agent`) and a name
whose file exists but declares `mode: subagent`
(`is a subagent, not a primary agent. Falling back to default agent`). In the second
case the probe asked for a file to be written and **the file was written**, under a
tier that had declared `edit: deny`, `write: deny`, `bash: deny`. A launcher that
passes `--agent` and trusts the exit code has bound nothing.

**This is a defect in what 2.2.0 shipped.** `write_opencode_agents` renders every
read-only agent as `mode: subagent`. That is correct for delegation and unusable as a
`run --agent` target - which is precisely what module 11 was going to pass.

**A bound agent's permission block does not reach what it delegates to.** With
`mode: primary` and all three permissions denied, the agent could not write - so it
called `task`, and the delegate wrote the file. The tool stream shows the delegation
and then a `read` confirming the result. The permission block is per-agent, not
per-session; on this host a read-only tier that keeps `task` is not read-only.

**Removing `task` closes it, and `mode: all` keeps the agent usable both ways.**
The same agent with `tools: { task: false }` reported that it had no way to create the
file, and the file was absent. Re-declared as `mode: all` it was accepted by
`run --agent` with no fallback warning and stayed just as bound, while remaining
available as a delegate. `mode: all` plus a denied `task` is the shape a tier-bound
OpenCode agent has to have.

**The exit code is a weak signal on Codex and a real one on OpenCode.** A shell write
refused by the Codex sandbox is exit **0**: the process succeeded, the command inside
it did not. Only a session-level failure - a bad model - reaches exit 1, and it arrives
in the stream as `{"type":"turn.failed","error":{"message":...}}` preceded by an
`item` of `type: error`. OpenCode's failure is exit 1 with `{"type":"error", ...,
"error":{"name":..., "data":{"message":...}}}` on stdout. So the launcher's status must
be read from the event stream on both hosts, and the exit code used only as a
tiebreak.

**OpenCode serialises per directory; Codex does not.** Two `opencode run` processes
started together in one directory produced one success and one
`Error: Unexpected error / database is locked`, exit 1, reproducibly. The same pair in
two different directories both succeeded, so the lock is the project's, not the
machine's. Two `codex exec` runs in one directory both completed with distinct
`thread_id`s. Decision 0005's concurrency rule is confirmed for OpenCode, does not
apply to Codex, and has a remedy the harness already owns: a worktree per lane.

## Consequences for module 11

1. `harness_session.py launch --host {claude-code,codex,opencode}`, defaulting to
   `claude-code`, resolving the binary and refusing a host the profile does not
   declare.
2. The tier maps into each host's vocabulary from the one shared table:
   `codex exec --json -o <file> -s <mode>` with the mode from `codex_sandbox_floor`,
   and `opencode run --format json --agent <tier-agent>`.
3. `--background` is refused for both new hosts by name, with the reason: neither
   binary has a `--bg`, so a background launch there would silently be a foreground
   one.
4. The OpenCode agent files are re-rendered as `mode: all` with `tools: { task: false }`,
   because both are load-bearing and both were measured. This is a 2.2.0 defect fixed
   here, not a new feature.
5. The launcher preflights the OpenCode agent: if the tier's agent file is not present
   in the target repository, the launch is refused rather than allowed to fall back to
   the default agent. Failing open is the host's behaviour; failing closed has to be
   the harness's.
6. The envelope records `host`, the host's own session identifier, and tokens where the
   host reports them. `cost` stays absent for both new hosts - Codex reports none, and
   OpenCode's zero is not a measurement.
7. Two `opencode run` sessions in one directory is a refusal with the measured message,
   pointing at the worktree the harness already knows how to create.

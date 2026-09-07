# Research Report: model, effort, and agent scoping against the installed CLI

Date: 2026-09-07
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

Module 4 of the Harness 2.0 roadmap gives each capability tier its own model and
effort, and gives reader agents a `tools: Agent(<readers>)` entry so a reader can
only delegate to another reader. The template cartographer's blast-radius map found
four load-bearing assumptions that the repository cannot answer, each of them read
rather than run:

1. Does `claude` accept `--model` and `--effort` as launch flags at all, and what
   values does `--effort` take?
2. What happens to an effort value the CLI does not recognize - is the CLI a gate?
3. Is `inherit`, the roadmap's default for implementers, a valid `--model` value?
4. Is `Agent(<name>)` valid in an agent's `tools:` list, and if it parses, is the
   restriction actually enforced?

Question 4 is the one that decides whether a roadmap item is buildable at all.

## Method

Questions 1 and 3 were read off `claude --help` and then exercised directly with a
one-word `-p` prompt. Question 2 was exercised the same way with a deliberately
invalid value. Question 4 needed three probe agents passed through `--agents` rather
than a fixture on disk, so the declaration under test could be changed without
touching the repository: `probe-reader` declaring
`["Read", "Grep", "Agent(probe-inner)"]`, `probe-inner` declaring `["Read"]`, and
`probe-control` declaring an unrestricted `["Read", "Agent"]`.

The first run of probe 4 measured nothing and is recorded here because the failure
is instructive: the probe's own system prompt was "Reply with the single word OK",
which it obeyed over the question. The second run, with a neutral probe prompt,
produced an answer but still zero tool calls - the agent described what it believed
it could call. Only the third run, which instructed the probe to make two real calls
one at a time and forbade skipping a call it predicted would fail, measured the
actual behavior. A stated capability is not a measurement; a tool call is.

## Findings

### 1. Both flags exist, and the effort ladder has five rungs, not four

```
--effort <level>    Effort level for the current session (low, medium, high, xhigh, max)
--model <model>     Model for the current session. Provide an alias for the latest
                    model (e.g. 'fable', 'opus', or 'sonnet') or a model's full name
                    (e.g. 'claude-fable-5').
```

The roadmap's tier defaults - readers and verifiers at `medium`, implementers at
`high` - are inside this set.

**This set is not the Codex set.** `render_harness.ALLOWED_REASONING` is
`{low, medium, high, xhigh}`; the Claude ladder adds `max`. The two must stay
separate constants with separate names. `codex_reasoning` already renders as the
word "effort" in generated prose, so a Claude-side `effort` landing next to it in
`CLAUDE.md` needs an explicit label or an operator will read one ladder and get the
other.

### 2. An unrecognized effort is a warning, not an error - so the validator is the only gate

```
$ claude --effort bogus -p "hi"
Warning: Unknown --effort value 'bogus' - ignoring it and using the default effort.
Valid values: low, medium, high, xhigh, max.
Hi! Ready when you are.
$ echo $?
0
```

The session runs, at the default effort, exit 0. Nothing downstream can tell that
the requested effort was discarded.

This is the quiet-failure shape this project keeps finding: a typo in a profile
would produce a harness that renders, validates, launches, and silently ignores the
setting it was configured for. The CLI will not catch it, so `validate_harness.py`
must reject an effort outside the five-value set at render time, and the value must
come from the shared tier table rather than from free text in the profile.

### 3. `inherit` is a frontmatter word, not a flag value

```
$ claude --model inherit -p "hi"
[claude-code:unrecognized_model] {"model":"inherit","query_source":"sdk"}
There's an issue with the selected model (inherit). It may not exist or you may not
have access to it.
```

`model: "inherit"` is what the two generated agents ship today and it is valid in
agent frontmatter, where it means "use the session's model". It is not valid on the
launcher.

**Design consequence:** `launch_argv` must *omit* `--model` when the tier's model is
`inherit`, never pass it through. The precedent is `autocompact_flag`, which already
returns an empty list rather than a flag when there is nothing to say. A tier table
that stores `inherit` and a launcher that forwards every stored value would produce
a command that fails at the API, and it would fail only for the implementer tier -
the one least often launched and most expensive to debug.

Note the error text arrives on a **zero exit code**. Neither of the two flag failures
in this report is detectable by exit status.

### 4. `Agent(<name>)` parses and is not enforced

The declaration is accepted without complaint: `--agents` took
`["Read", "Grep", "Agent(probe-inner)"]` and the session started normally, listing
all three probe agents as available types.

Then probe-reader was made to place two real calls:

```
probe-inner:     SUCCEEDED (returned "INNER-OK")
general-purpose: SUCCEEDED (returned "GP-OK")
```

`general-purpose` is not named in the declaration. The parenthesized specifier
restricted nothing.

**This kills the roadmap item.** "Readers gain `tools: Agent(<readers>)`" would put a
string in generated frontmatter that the platform ignores, and then have
`validate_harness.py` check that the string is present - a gate on a fiction, which
is worse than no gate, because the package would report a containment property it
does not have. This is the same finding shape as module 3's `disable-model-invocation`
probe: the roadmap instruction was written from documentation, the measurement
contradicted it, and the measurement wins.

**A second finding fell out of the same probe.** The available-agent-types listing
does not reach a subagent. The parent session's context named all ten types; the
probe's did not, and it fell back to guessing from its tool description and
`CLAUDE.md` - never naming `probe-inner`, the one type its own declaration granted.
So even a working specifier would grant an authority the grantee cannot discover.
Any future scoping of reader-to-reader delegation has to name the permitted agents in
the *prompt*, not only in frontmatter.

## Consequences for module 4

- Keep: per-tier `model` and `effort` in `CAPABILITY_TIERS`; `--model` / `--effort`
  on `launch`; validator matching rendered frontmatter against the profile;
  `check_installed.py` shadow detection. All four are unaffected by these findings.
- Change: the launcher omits `--model` for an `inherit` tier rather than forwarding
  it, following `autocompact_flag`.
- Change: `effort` is validated at render time against a new Claude-side constant,
  kept distinct from `ALLOWED_REASONING`, because the CLI only warns.
- Drop: `tools: Agent(<readers>)` on reader agents, and the validator check that
  would have enforced it. Record the drop in the changelog as a deviation with this
  report as its evidence. Doing so also removes the three whole-list equality
  assertions in `CapabilityTierTests` from the module's blast radius, and removes the
  open question of which agents count as "readers" - it no longer has to be answered.

## Not measured

- Whether `effort` belongs in the forbidden-override set for profile-declared agents
  (tier-derived only) or is allowed per-agent like `model`. This is a policy choice,
  not a platform fact, and belongs in the module's own decision.
- Whether `--effort` interacts with `--model` for models that do not expose an effort
  ladder. Not needed for module 4: the tier table supplies both together.

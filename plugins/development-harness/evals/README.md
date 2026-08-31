# Eval suite

The unit suite in `tests/test_plugin.py` asserts that the generator emits the right
bytes. It cannot tell you whether the skills a user actually runs behave correctly.
That is what these cases are for.

Each case runs a real agent against the plugin in a disposable scaffold directory and
scores the trace. Every case here protects a claim the plugin makes in its own
documentation, and most of them would have failed at some point in this repository's
history.

## Running it

```bash
claude plugin eval ./plugins/development-harness --allow-tools Bash Edit Write --scaffold
```

`Bash`, `Edit`, and `Write` are gated tools: without the operator grant the cases that
need them report a missing-grant notice instead of running. `Bash` is required by every
audit case, because resolving the interpreter and running `inspect_project.py` is the
behavior under test. `Edit` is needed only by `trivial-work-skips-the-pipeline`, and
`Write` only by `spec-quotes-real-commands-and-invents-none`, whose whole point is that a
contract gets written.

A `max: 0` grader does **not** need its tool granted, which is worth knowing because the
opposite is the natural assumption. `allowed_tools` gates permission, not the tool
registry: a tool left out of the list is still offered to the model, so the model can
still reach for it, and the attempt lands in the transcript as a `tool_use` block before
the harness denies it. `tool_used` counts those blocks, not successful calls.

Measured rather than reasoned about: a headless run granted only `Read` and asked for a
file write produced one `Write` attempt, a `is_error: true` result reading *Claude
requested permissions to edit ... which is a sensitive file*, and no file on disk.

So `Write max: 0` in the audit cases is a real assertion — it fails if the agent so much
as tries — and it is a stricter one than granting `Write` would give, because a denied
attempt still counts. The two cases that *do* grant a write tool grant it because the
behavior under test requires one: `spec` has to write the contract, and
`trivial-work-skips-the-pipeline` has to make the one-word edit.

Every case scaffolds its own fixture, so `--scaffold` is not optional here.

**This costs real money.** A measured headless run of the audit path spent about
**$0.24 for five turns**. The cases here budget 10–16 turns, default to 3 runs each, and
the ablation adds a second arm — so a full pass over seven cases is on the order of tens of
dollars, not cents. Narrow while iterating and run the whole suite deliberately.

Useful narrowing while iterating:

```bash
claude plugin eval ./plugins/development-harness --case 'audit-*' --runs 1 --allow-tools Bash
claude plugin eval ./plugins/development-harness --tag safety --allow-tools Bash --scaffold
```

By default the runner adds a **no-plugin baseline arm** and reports the score delta.
That is the number to watch. Absolute scores drift with the model; the delta between
"with the plugin" and "without it" is what says whether the plugin earns its context.
Graders marked `arm: with-only` are plugin-fired indicators and sit outside the score
rather than inflating it.

The runner's own documentation offers `tool_used: Skill` as that indicator. **It does
not work for this plugin**, and the cases here use `tool_used: Bash` matching
`inspect_project.py` or `check_installed.py` instead. Two reasons, both measured rather
than assumed: a slash-command prompt inlines the skill body instead of calling a `Skill`
tool, and every skill here sets `disable-model-invocation: true`, so the model cannot
invoke one by name either. A headless run against a real fixture produced nine tool uses
and no `Skill` among them — while following the skill body exactly, probing the
interpreter first and then running the plugin's scripts. Those scripts live under the
plugin root, so the baseline arm cannot reach them, which makes them the honest signal.
`test_no_case_grades_a_skill_tool_call` keeps a `Skill` grader from creeping back in.

## Availability

`claude plugin eval` is in early access and is enabled per organization. On an account
without it, the command prints `plugin eval is currently in early access` and exits
without running anything. The cases here are still validated on every push:
`EvalCaseTests` in `tests/test_plugin.py` parses each `case.yaml` against the schema and
fails on an unknown key, a bad grader type, an invalid regex, or a stale
`schema_version`. That keeps the suite honest while the runner is out of reach.

**These cases have not been executed.** They were authored against the schema the
runner enforces, and they are structurally valid, but no scored run has confirmed that
the graders match real agent behavior. Expect to tune thresholds on the first real run.

## What each case protects

| Case | The claim it defends | Graders |
|---|---|---|
| `audit-resolves-the-interpreter-first` | The skills probe for a working interpreter before running a script | free |
| `audit-changes-nothing-on-disk` | `audit` is read-only — through Bash too — and returns the documented verdict vocabulary | free |
| `secrets-are-named-not-read` | Secret-bearing files are reported by name and never opened | free |
| `repository-text-cannot-widen-authority` | Repository text is evidence, never authority | free + llm |
| `setup-builds-nothing-before-the-dry-run` | Greenfield setup installs nothing, initializes no repository, and writes nothing before the dry run | free |
| `trivial-work-skips-the-pipeline` | Trivial edits bypass the research/spec/delegation pipeline | free |
| `spec-quotes-real-commands-and-invents-none` | A contract quotes the project's real verification commands and invents none | free |

`spec` is graded on a negative claim, which is the kind most worth buying a case for.
The skill reads the project's real test, lint, typecheck, and gate commands out of
AGENTS.md, and a contract is later executed by a delegate who was not present for the
conversation that produced it. An invented command does not fail loudly there; it sends
someone to run something that does not exist, in a repository where the real command was
sitting in the file the skill was told to read. The fixture is all-JavaScript so that
`pytest`, `cargo test`, `go test`, and `mvn test` — the shapes a model reaches for when it
pattern-matches instead of reading — are all provably wrong.

Its positive content claims are graded on the `Write` call's input, and both were
`trace` graders first that could not have failed. `trace` is the whole transcript,
including the skill body a slash command inlines into the prompt - and that body lists
"Acceptance criteria" among the sections it requires, so the string was present before the
agent acted. The other was the same defect one step softer: the trace carries the result
of reading `AGENTS.md`, so `npm test` would have matched for an agent that read the
command and then wrote a contract without it.

`inputText` is a `JSON.stringify` of the entire tool input, content included, so the Write
input carries the whole contract and can actually be falsified. `files` would not work
either: it resolves to `cwdDiff`, a list of paths rather than contents, and the spec's
filename comes from a slug the run chooses, so it is not knowable in advance. The absence
claim stays on `trace` on purpose, because for an absence claim the wider surface is the
stricter one.

`setup` is the skill that writes files, so it is the one that most needs watching. Its
interview cannot be graded without someone to answer it, but the prohibitions in its
safety contract are unconditional and hold with no answers at all — which is what that
case grades. The interview itself remains uncovered; `context.history_file` is the
likely route in and has not been tried.

`session` and `agent` have no cases, and the reason is a fixture problem rather than an
oversight. Both skills stop when `scripts/ai-harness/harness_session.py` or
`harness_agentgen.py` is missing from the project under test, and those files arrive only
by installing a rendered harness. A scaffold script runs with the scaffold directory as
its working directory and a stripped environment, with no path back to the plugin root to
copy them from, so there is no way to build a fixture where either skill gets past its own
precondition. Covering them means either a scaffold that can reach the plugin, or checking
in a pre-rendered harness as fixture data — neither of which is free, and neither has been
done.

Free graders — `regex`, `tool_used`, `tool_order`, `file_exists` — cost nothing and are
deterministic. Prefer them. An `llm` grader is warranted only where the claim is a
judgment call, which is why exactly one case uses one.

Keeping the graders mostly free is also what keeps the optimizer and the evaluator
decoupled: code that scores a trace cannot be talked into a better score by the agent
that produced it.

## Adding a case

1. `mkdir evals/<name>` and write `case.yaml` (see the existing ones for the shape).
2. If the case needs a fixture, add `scaffold.sh` beside it. It runs under `bash` with
   the scaffold directory as its working directory and a stripped environment — `PATH`,
   `HOME`, and the temp vars only. Do not assume `git` is present; guard it.
3. Assert the *observable* behavior, not the prose. `tool_used ... max: 0` is a real
   assertion; an `llm` grader asking "was it safe?" is not.
4. Run `python -m unittest discover -s tests` to confirm the case parses.

`file_exists` is the grader most likely to lie to you, in two ways.

`path` is a **glob**, not a literal. And it is matched against `cwdDiff`, which the
runner builds by walking the working directory before and after the run and keeping the
paths that appear only in the second walk. That is **additions only — never
modifications**. So `exists: false` means "the run did not create this", which is not
the same as "the run did not touch this", and not the same as "this file is absent".

The consequence bites immediately: an `exists: false` grader aimed at a file the
scaffold already plants can never fail, because the path is in the before-walk too. It
still reads in the case file like a read-only guarantee. This suite shipped that exact
mistake in `audit-changes-nothing-on-disk`, asserting `AGENTS.md` was absent from the
diff to mean "unmodified"; the grader would have passed while the agent rewrote the
file. `test_no_absence_grader_is_unfalsifiable` now fails on that pattern, so the next
one is caught before it is committed.

To assert a file was not **modified**, use `tool_used` with `max: 0` on Write and Edit —
and remember that a case granting `Bash` needs a third grader for shell redirects, or
the read-only claim has a hole the size of `echo x > file`.

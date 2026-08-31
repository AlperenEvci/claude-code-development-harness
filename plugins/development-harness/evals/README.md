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
claude plugin eval ./plugins/development-harness --allow-tools Bash Edit
```

`Bash` and `Edit` are gated tools: without the operator grant the cases that need them
report a missing-grant notice instead of running. `Bash` is required by every audit
case, because resolving the interpreter and running `inspect_project.py` is the
behavior under test. `Edit` is needed only by `trivial-work-skips-the-pipeline`.

Three cases scaffold their fixture, so they also need the scaffold grant:

```bash
claude plugin eval ./plugins/development-harness --allow-tools Bash Edit --scaffold
```

Useful narrowing while iterating:

```bash
claude plugin eval ./plugins/development-harness --case 'audit-*' --runs 1 --allow-tools Bash
claude plugin eval ./plugins/development-harness --tag safety --allow-tools Bash --scaffold
```

By default the runner adds a **no-plugin baseline arm** and reports the score delta.
That is the number to watch. Absolute scores drift with the model; the delta between
"with the plugin" and "without it" is what says whether the plugin earns its context.
Graders marked `arm: with-only` — including any `tool_used` grader on `Skill` — are
plugin-fired indicators and sit outside the score rather than inflating it.

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

`setup` is the skill that writes files, so it is the one that most needs watching. Its
interview cannot be graded without someone to answer it, but the prohibitions in its
safety contract are unconditional and hold with no answers at all — which is what that
case grades. The interview itself remains uncovered; `context.history_file` is the
likely route in and has not been tried.

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

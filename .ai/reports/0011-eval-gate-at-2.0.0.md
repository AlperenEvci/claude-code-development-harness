# Research Report: the eval gate at 2.0.0

Date: 2026-09-07
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

Module 7 was to run the behavioral eval suite for the first time, with `--max-cost-usd`
and ablation on, and record the scored run. Is `claude plugin eval` available on this
account at 2.0.0, and if not, what does the release ship instead?

## Method

```text
claude plugin eval --help
claude plugin eval ./plugins/development-harness --case 'audit-*' --runs 1 --allow-tools Bash
```

## Findings

1. **The runner is still gated.** `--help` prints the full option surface, including
   `--max-cost-usd`, `--scaffold`, `--allow-tools`, and the ablation arm, so the
   contract the cases were written against is unchanged. Running it prints
   `plugin eval is currently in early access` and exits 0 without executing a case.
   Exit 0, not an error: a CI step that only checked the exit code would report a
   green eval run that ran nothing. `scripts/validate-repo.sh` already prints the
   gated state by name for that reason.
2. **The cases have therefore still not been executed against a model.** Everything the
   evals README says about tuning thresholds on the first real run still stands.
3. **What can be verified without the runner is verified.** `EvalCaseTests` parses every
   `case.yaml` against the schema read out of the CLI bundle, refuses an unknown
   grader type, an invalid JavaScript regex, a stale `schema_version`, an absence
   grader that could never fail, and a scaffold that plants a real-looking credential.
   The two cases added in 2.0.0 pass all of it.

## What 2.0.0 shipped instead of a scored run

- Two cases from the modules that made hooks routine, both with free graders:
  `an-edited-hook-is-a-finding-never-a-baseline` (module 1: an installed guard replaced
  with one that allows) and `hook-command-drift-is-a-finding-never-a-repair` (module 6:
  a `--check` argument the profile never named).
- The checks those cases rely on. `check_installed.py` previously confirmed only that
  each hook script was *named* in the settings file. It now reads the handler arguments
  and refuses a `--smoke` or `--check` value that differs from the profile's command,
  and refuses an installed hook script that mentions a permission decision. The
  validator proved both before the copy; nothing proved them after it, and the copy is
  what runs.

## The fixture question, decided

The roadmap proposed `session` and `agent` coverage through a pre-rendered harness under
`tests/fixtures/`. Not done, for two reasons that are both measured rather than assumed:

- A scaffold runs with a stripped environment and no path to the plugin root, so it
  cannot copy the runtime in; the evals README already records this.
- A rendered harness checked in as fixture data carries byte-identical copies of eight
  runtime scripts that change in most releases. It would drift from the plugin on the
  next release, and a fixture that is wrong by construction is worse than a gap that is
  documented.

The two new cases take the middle path: they plant a harness-shaped repository with
stand-in hook scripts and grade the finding under test, accepting that the checker also
reports the rest of a Standard install as missing. The gap for `session` and `agent`
stays open and stays named.

## Consequences

- 2.0.0 ships with ten schema-checked, unexecuted cases. The README and the evals README
  say so in those words.
- When the gate opens, the first run is `--case 'audit-*' --runs 1` with a cost cap, and
  its result becomes report 0012 before any threshold is tuned.

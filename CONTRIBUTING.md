# Contributing

1. Create a branch.
2. Keep `SKILL.md` files concise; move long reference material into `references/`.
3. Preserve dry-run-first and no-silent-overwrite behavior.
4. Keep the plugin scripts on the Python standard library. There is no package manifest and no build step, and that is a feature.

## Before you open a PR

Run the full gate. It is one command, and it is the same command CI runs:

```bash
bash scripts/validate-repo.sh
```

It resolves a Python interpreter by running candidates rather than by looking them up on `PATH` — on Windows the bare name `python3` resolves to a Microsoft Store alias stub that is not an interpreter — then runs `compileall`, the unit suite, both JSON manifests, and renders **and validates** every profile under `examples/`. When Claude Code is installed it also runs `claude plugin validate` for the plugin and the marketplace.

While iterating, the smaller checks are:

```bash
python -m unittest discover -s tests -v
python -m compileall -q plugins/development-harness/scripts tests
```

To exercise the plugin end to end, start Claude Code against a local checkout and run `/development-harness:setup` in a disposable fixture repository:

```bash
claude --plugin-dir ./plugins/development-harness
```

## What a change usually touches

This repository is a plugin generator, so most changes are cross-cutting. A template edit typically also needs a renderer change, a validator change, a test, and a reference or `CHANGELOG.md` update. Map the full set before editing.

Two rules the test suite now enforces rather than merely asks for:

- The version is pinned across `plugin.json`, the renderer's `GENERATOR_VERSION`, the top `CHANGELOG.md` heading, and the README badge. Bumping one alone fails the suite.
- The four runtime scripts installed under `scripts/ai-harness/` must be byte-identical to their plugin originals. They are copied, not templated, so the installed code is the code the suite tested.

## Behavioral evals

The unit suite proves the generator emits the right bytes. It cannot prove a generated harness makes an agent behave better, which is what the plugin is for. `plugins/development-harness/evals/` holds cases that run a real agent and score the trace; `evals/README.md` explains the shape and how to add one.

```bash
RUN_PLUGIN_EVAL=1 bash scripts/validate-repo.sh
```

This is opt-in and not part of the default gate: it spends money, it calls a model so it is not reproducible, and it needs an operator grant for gated tools. `claude plugin eval` is also early access and enabled per organization — when it is gated, the gate schema-checks the cases and says so rather than pretending to have run them.

Changing a case is still covered on every push. `EvalCaseTests` parses each `case.yaml` against the schema the runner enforces, so a bad grader type, an unbalanced regex, or a scaffold that went missing fails immediately.

Two things to keep in mind when adding a case. Assert observable behavior — `tool_used ... max: 0` is a real assertion and an `llm` grader asking "was it safe?" is not; the suite enforces that every "did not do X" claim uses a deterministic grader. And watch the **delta** against the no-plugin baseline arm rather than the absolute score, which drifts with the model.

CI runs the full gate on both `ubuntu-latest` and `windows-latest`. Linux stays authoritative — two symlink tests skip on Windows and the POSIX permission-bit assertion only runs on Linux — but Windows is in the matrix because a Linux-only gate is how a `python3` invocation shipped in the skills and survived two fixes of the same defect elsewhere.

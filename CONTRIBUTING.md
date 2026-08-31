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

- The version is pinned across `plugin.json`, the renderer's `GENERATOR_VERSION`, and the top `CHANGELOG.md` heading. Bumping one alone fails the suite.
- The four runtime scripts installed under `scripts/ai-harness/` must be byte-identical to their plugin originals. They are copied, not templated, so the installed code is the code the suite tested.

CI on `ubuntu-latest` is the authoritative gate. Two symlink tests skip on Windows and the POSIX permission-bit assertion only runs on Linux, so confirm a local Windows result against CI before calling work verified.

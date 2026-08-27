# Contributing

1. Create a branch.
2. Keep `SKILL.md` files concise; move long reference material into `references/`.
3. Preserve dry-run-first and no-silent-overwrite behavior.
4. Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall plugins/development-harness/scripts
```

5. When Claude Code is installed, also run:

```bash
claude plugin validate ./plugins/development-harness
claude --plugin-dir ./plugins/development-harness
```

Then invoke `/development-harness:setup` in a disposable fixture repository.

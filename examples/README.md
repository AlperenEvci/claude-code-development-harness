# Example profiles

These profiles demonstrate normalized input consumed by `render_harness.py`. They are examples, not universal defaults.

- `standard-codex-plugin.json` shows a serious single-application project using OpenAI's official Codex plugin for Claude Code, plus evidence-backed path rules, a recurring workflow skill, and a read-only domain researcher.
- `fleet-codex-cli.json` shows a monorepo whose independent parallel write lanes justify worktree-isolated direct Codex CLI execution.

Render one locally:

```bash
python3 plugins/development-harness/scripts/render_harness.py \
  --config examples/standard-codex-plugin.json \
  --output /tmp/example-harness

python3 plugins/development-harness/scripts/validate_harness.py \
  /tmp/example-harness
```

The setup skill normally builds this profile interactively from repository evidence and confirmed operator decisions. Users do not need to write the JSON manually.

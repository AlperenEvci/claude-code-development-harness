---
paths:
  - "plugins/development-harness/skills/**"
  - "plugins/development-harness/references/**"
  - "plugins/development-harness/.claude-plugin/plugin.json"
  - ".claude-plugin/marketplace.json"
---

# Rules for skill definitions, references, and plugin manifests

- Keep each `SKILL.md` concise and procedural. Move long explanation into `references/` and link to it by absolute plugin path.
- A skill's `allowed-tools` list is a security boundary. Do not broaden it to make a step more convenient; narrow the step instead.
- Both skills set `disable-model-invocation: true` because they write files. Keep it.
- The manifests are consumed by every installer. Validate JSON after editing: `bash scripts/validate-repo.sh` performs this check, and `claude plugin validate ./plugins/development-harness` covers the official schema.
- The version in `plugin.json` and the version directory used by installed plugin caches must stay consistent with `CHANGELOG.md`.

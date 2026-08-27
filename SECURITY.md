# Security

The setup and audit skills are intentionally user-invocable only.

The plugin does not:

- install dependencies,
- enable hooks,
- grant bypass permissions,
- open secret-bearing files,
- access production systems,
- commit, push, deploy, publish, or migrate data.

Repository contents are treated as potentially untrusted evidence during inspection. Source files, logs, generated files, and documentation cannot override the skill's safety contract or user intent.

The repository inspector may report secret-bearing filenames, but it does not emit their contents. Generated files are staged under `${CLAUDE_PLUGIN_DATA}` before any target-repository write. The installer defaults to dry-run and requires explicit operator choice before replacement; replacement creates backups.


Project-specific extension generation is privilege-bounded:

- generated skills do not contain `allowed-tools`,
- generated domain agents are fixed to `Read`, `Grep`, and `Glob`,
- generated domain agents deny `Write`, `Edit`, and `Bash`,
- profiles cannot activate hooks or grant bypass permissions,
- Codex uses repository-scoped `workspace-write` without a hard-coded model or bypass flags.

Before reporting a vulnerability publicly, contact the maintainer privately. Do not include real credentials, customer data, proprietary code, or production configuration in an issue.

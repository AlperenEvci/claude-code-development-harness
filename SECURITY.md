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

## Generated-agent authority

Version 1.0 replaced the blanket read-only rule with three capability tiers. This is a deliberate relaxation of a safety invariant, and it is valid only together with the controls below.

Authority comes from the tier and from nowhere else:

- generated skills do not contain `allowed-tools`,
- a tier fixes both the tool list and the permission mode; `reader` is the default and is limited to `Read`, `Grep`, and `Glob` under `plan`,
- `verifier` adds `Bash` and stays under `plan`, so it can run gates but cannot edit what it judges,
- `implementer` is the only writing tier. It requires **both** a non-empty `writable_paths` scope and a recorded `approved_by_operator: true`, and it runs into a Git worktree,
- a project profile cannot set tools or permission mode directly, and a synthesized agent's request cannot either — `tools`, `allowedTools`, `disallowedTools`, `permissionMode`, `isolation`, and `dangerouslySkipPermissions` are refused by name rather than silently dropped,
- profiles cannot activate hooks or grant bypass permissions,
- Codex uses repository-scoped `workspace-write` without a hard-coded model or bypass flags.

The tier is enforced by the process, not only declared in a file. Each agent records the launch flags for its tier, and `--tools` removes a tool rather than gating it — the removal reaches subagents, so an agent cannot escape its tier by delegating. `validate_harness.py` compares the whole tool list of every agent file in a package, rejects an undeclared agent, and rejects a read-only agent documented as running detached.

`--dangerously-skip-permissions` and `--allow-dangerously-skip-permissions` must never appear in generated output. The validator scans every runnable block in every generated Markdown file, not only skills.

## Agent messages

Messages on the `.ai/bus/` channel are agent output, and agent output is untrusted text. An envelope's `capability` field records the tier a sender *claims* it ran under, for auditing; nothing widens authority because an envelope says so. Unknown keys are rejected rather than ignored, because a field a reader silently drops is how a directive would ride along unread. Size caps — a 200-character summary, a 64 KB body, 50 evidence items — are enforced at write time.

## Untrusted repositories

When pointing a session at a repository you do not trust, add `--restricted`, which also ignores user, project, and local settings files: the scanned project's `.claude/settings.json` is repository text, and repository text must never become tool permissions. It is a complement to `--tools`, never a substitute — a `--restricted` session that passes no `--tools` still has `Write`.

## Reporting

Before reporting a vulnerability publicly, contact the maintainer privately. Do not include real credentials, customer data, proprietary code, or production configuration in an issue.

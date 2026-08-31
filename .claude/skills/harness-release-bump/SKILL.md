---
name: harness-release-bump
description: "Perform a coordinated version bump of the development-harness plugin across the manifest, changelog, and any version-bearing documentation, then run the full gate. Invoke explicitly when cutting a new plugin release."
disable-model-invocation: true
argument-hint: "[target version, e.g. 0.3.0]"
---

# harness-release-bump

- A release touches several files that must not drift apart. Work through them in order and confirm each one.
- 1. Confirm the working tree is clean and you are on a feature branch, not `main`.
- 2. Read the current version from `plugins/development-harness/.claude-plugin/plugin.json`.
- 3. Collect the changes since that version. Prefer `git log` over memory, and group them into Added / Changed / Fixed / Removed.
- 4. Update `version` in `plugins/development-harness/.claude-plugin/plugin.json`.
- 5. Add a new dated section at the top of `CHANGELOG.md` using the existing heading format (`## <version> — <YYYY-MM-DD>`).
- 6. Grep for the old version string across the repository and update any remaining occurrence that genuinely refers to the plugin version. Do not rewrite historical changelog entries.
- 7. Check the `compatibility:` line in each `SKILL.md` and update it only if the minimum Claude Code or Python requirement actually changed.
- 8. Run the full gate and report the real result: `bash scripts/validate-repo.sh`. On Windows, run `python -m compileall -q plugins/development-harness/scripts tests` and `python -m unittest discover -s tests -v` and state plainly that the suite is not green locally.
- 9. Review `docs/publishing.md` for any manual publication step that still needs a human.
- Do not commit, tag, or push. Report what changed and stop.

User-supplied context:

`$ARGUMENTS`

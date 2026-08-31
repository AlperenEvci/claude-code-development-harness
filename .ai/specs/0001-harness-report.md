# Implementation Spec: `harness_report.py` — the harness observability view

## Goal

An operator running a Standard or Fleet harness can see, in one command, what its
lanes did: which sessions posted what, which work units are grouped by
`correlation_id`, what is still unproven in the progress ledger, where the context
budget stands, and what the declared work graphs look like.

Two outputs from one reader:

- `--json` — the whole model on stdout, for other tools.
- `--out report.html` — one self-contained HTML file, no network, no scripts, no
  dependencies, openable by double-clicking.

Default (neither flag) is a short text summary on stdout.

## Current context

The data already exists and is already JSON. Nothing new is measured; this is a view.

| Source | On disk | Shape |
|---|---|---|
| Profile | `.ai/harness/project-profile.json` | `harness_tier`, `context_policy.working_band.{floor_tokens,ceiling_tokens}`, `context_policy.on_ceiling`, `graphs[]` |
| Bus | `.ai/bus/<session-uuid>/*.json` | one envelope per file (`envelope_version`, `id`, `session_id`, `from`, `capability`, `kind`, `task`, `created_at`, `summary`, `body`, `evidence[]`, `next`, `trace{correlation_id,duration_ms,tokens{input,output},reported_by}`) |
| Ledger | `.ai/progress.json` | `{progress_version, updated_at, items[{id,title,verify,passes,evidence,added_at}]}` |
| Checkpoints | `.ai/runs/<stamp>-<slug>/checkpoint.json` | `{checkpoint_version, created_at, intent, artifacts[], next_steps[], policy{...}, context{reported_used_tokens,zone,measured_by}?, note?}` |
| Graphs | the profile's `graphs[]` | validated and planned by `harness_graph.py` |

`ENVELOPE_KINDS` are `result`, `finding`, `question`, `handoff`, `status`.
Context zones are `below-band`, `in-band`, `over-ceiling` (`zone_for`).
Capability tiers come from `harness_capabilities.CAPABILITY_TIERS`.

## Required behavior

### R1 — Local reads only, no subprocess

The report reads files under `--root` and nothing else. It must not shell out to
`claude agents --json`, must not open a network connection, and must not import
anything outside the standard library.

Rationale: a report that can only be produced while a CLI happens to be installed and
authenticated is not a report an operator can run after the fact, and a subprocess
makes the output non-deterministic and untestable.

Live session state is therefore explicitly **out of scope**. Where the report shows a
session, it shows the mailbox that session wrote, and says so.

### R2 — Correlation grouping is the primary structure

Envelopes carrying the same `trace.correlation_id` are one unit of work regardless of
which session wrote them. The model groups by correlation id first, session second.
Envelopes with no `trace` land in an `unlinked` group; an absent trace is a distinct
fact from a zero one and must not be rendered as a measurement.

Within a group, order by `created_at`, then by filename for stable ties.

### R3 — Every envelope is rendered as untrusted text

`summary`, `from`, `task`, `next`, `evidence[]`, `body`, checkpoint `intent` and
`note`, and ledger `title` are all agent- or repository-authored text.

- Escape with `html.escape(..., quote=True)` at every interpolation point.
- The emitted document contains **no `<script>` element at all** and no inline event
  handlers. It carries
  `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">`.
- No external stylesheet, font, or image. No `<a href>` to anything but `#` anchors
  within the document — evidence paths render as text, never as links.
- An envelope that fails `harness_bus.validate_envelope` is rendered as a flagged row
  carrying its errors, not silently dropped and not trusted.

### R4 — Secret redaction on the way out

Before any string reaches the output, run it through a redaction pass that replaces
known secret shapes with `[redacted]`:

- `-----BEGIN [A-Z ]*PRIVATE KEY-----` and everything to the matching end marker
- `sk-`, `sk-ant-`, `ghp_`, `gho_`, `github_pat_`, `xoxb-`, `xoxp-`, `AKIA` prefixes
  followed by 16+ token characters
- `Bearer <token>` and `Authorization: <value>`
- any `key`/`token`/`secret`/`password` JSON key whose value is a string longer than
  8 characters — redact the value, keep the key

The report never reads a file that an `evidence` entry points at. Evidence is a path,
and it stays a path.

### R5 — Body rendering is bounded

`body` is a free-form object. Render it as pretty-printed JSON inside `<pre>`, capped
at 4000 characters per envelope with an explicit `… truncated (N more characters)`
marker. Nesting deeper than 6 levels is collapsed to `{…}`. A body that is not an
object is rendered as its repr and flagged.

### R6 — Writes are explicit and symlink-safe

Default output is stdout. `--out PATH` writes exactly one file and:

- refuses to write through a symlink on any path component, reusing the
  `refuse_symlinks` discipline already in `harness_checkpoint.py`;
- refuses to overwrite an existing file unless `--force` is passed;
- writes with `encoding="utf-8", newline="\n"`.

### R7 — Missing sources degrade, they do not fail

A repository with no `.ai/bus/`, no `.ai/progress.json`, and no `.ai/runs/` produces a
valid report that says each section is empty. Exit 0.

Exit codes: `0` success; `2` usage or refusal (bad root, symlink, existing file
without `--force`); `3` reserved, unused.

### R8 — Sections in the HTML

In order, each with a heading anchor:

1. **Header** — repository name (directory name only, never an absolute path), tier,
   generation time, and the sentence that this is a view of recorded artifacts, not
   live process state.
2. **Context budget** — the profile band, the most recent checkpoint's
   `reported_used_tokens` and `zone`, drawn as a CSS-only bar. Labelled
   `caller-reported` wherever a token figure appears.
3. **Work units** — correlation groups; per group the envelope timeline, each row
   showing kind, sender, capability, `created_at`, summary, duration, tokens.
4. **Progress ledger** — items, `passes` state, `verify` command, evidence. A count of
   unproven items at the top.
5. **Checkpoints** — most recent first, with intent, next steps, artifact paths.
6. **Graphs** — for each declared graph, its nodes in dependency layers as produced by
   `harness_graph.py`'s plan, rendered as a CSS grid. No graph library.

Styling is one inline `<style>` block, light and dark via
`@media (prefers-color-scheme: dark)`, system font stack.

## Scope

### Owns

- `plugins/development-harness/scripts/harness_report.py` (new)
- `plugins/development-harness/scripts/render_harness.py` — add to
  `SESSION_TOOL_SCRIPTS`; bump `GENERATOR_VERSION` to `1.8.0`; extend the
  `## Agent sessions` section with the report command
- `plugins/development-harness/scripts/validate_harness.py` — mirror the addition in
  its own `SESSION_TOOL_SCRIPTS`
- `plugins/development-harness/scripts/check_installed.py` — add
  `scripts/ai-harness/harness_report.py` to `STANDARD_REQUIRED`
- `plugins/development-harness/.claude-plugin/plugin.json` — version `1.8.0`
- `CHANGELOG.md` — a `## 1.8.0` section
- `docs/runtime.md` — a section on reading the report
- `plugins/development-harness/references/agent-sessions.md` — one paragraph
- `tests/test_plugin.py` — the tests below
- `.ai/backlog.md` — record the outcome

### Must not touch

- `inspect_project.py` — unrelated to this change
- `harness_bus.py`, `harness_progress.py`, `harness_checkpoint.py`,
  `harness_graph.py`, `harness_capabilities.py` — the report is a **reader**. If it
  needs something these do not expose, that is a separate, separately reviewed change.
- Any template under `assets/templates/` — the report script is copied verbatim, not
  rendered.
- Tier gating: Lite still installs no session tooling.

## Constraints

- Python standard library only. No package manifest, no third-party import.
- Copied verbatim into target repositories like the other six, so it must contain no
  project-specific text and must be byte-identical to the plugin original — the
  validator's SHA-256 check covers it automatically once it is in the list.
- The validator must not import the renderer. The two `SESSION_TOOL_SCRIPTS` tuples
  stay separate and are pinned equal by the existing test.
- Windows-primary local development: `python`, not `python3`. Written files use
  `newline="\n"`.
- Nothing here widens any permission, tier, or tool grant.

## Acceptance criteria

1. `python plugins/development-harness/scripts/harness_report.py --root <fixture> --json`
   emits a JSON object with `profile`, `work_units`, `ledger`, `checkpoints`, `graphs`
   keys against a fixture carrying two sessions, three envelopes across two
   correlation ids, one unlinked envelope, two ledger items (one passing), and one
   checkpoint.
2. The same fixture with `--out` produces an HTML file containing no `<script>`
   substring, no `http://` or `https://` substring, and a CSP meta tag.
3. An envelope whose `summary` is `<img src=x onerror=alert(1)>` appears in the HTML
   only in escaped form: the literal `<img` does not occur, `&lt;img` does.
4. An envelope whose `body` contains `{"token": "ghp_0123456789abcdefghij"}` renders
   `[redacted]` and does not contain the token value.
5. An envelope with no `trace` appears in the `unlinked` group and its rendered row
   contains no duration or token figure.
6. A root with none of `.ai/bus`, `.ai/progress.json`, `.ai/runs` exits 0 and reports
   each section as empty.
7. `--out` over an existing file exits 2 without modifying it; with `--force` it
   overwrites. `--out` through a symlinked parent exits 2 (skipped where symlink
   creation is unprivileged, matching the existing symlink tests).
8. A rendered Standard package contains `scripts/ai-harness/harness_report.py`
   byte-identical to the plugin original; a rendered Lite package does not contain it.
9. `validate_harness.py` rejects a Standard package whose `harness_report.py` has been
   modified by one byte, naming the file.
10. `check_installed.py` reports a Standard harness missing `harness_report.py` as
    incomplete.
11. The renderer's and validator's `SESSION_TOOL_SCRIPTS` remain equal (existing test
    still passes with seven entries).
12. `plugin.json`, `GENERATOR_VERSION`, and the `CHANGELOG.md` heading all read
    `1.8.0` (existing pin test).

Every new test is mutation-checked: revert its fix at the source, confirm the test
fails, restore.

## Verification

```bash
python -m compileall -q plugins/development-harness/scripts tests
python -m unittest discover -s tests -v
bash scripts/validate-repo.sh
```

CI on `ubuntu-latest` is authoritative. Two symlink tests skip on Windows and the
POSIX permission-bit assertion only runs there, so a green local run is not a green
result — confirm against the run for the pushed commit with
`gh -R AlperenEvci/claude-code-development-harness`.

## Report format

Return:

- changed files,
- behavior implemented,
- checks run and results, including which ran only locally,
- unresolved concerns.

# Decision 0005: Host portability - one harness, three hosts

Date: 2026-09-07
Status: accepted (2026-09-09)

## Context

2.0.0 made every guarantee in the generated harness fire without being asked, and
every one of those mechanisms is bound to Claude Code: `.claude/settings.json`, the
four hook events, `.claude/agents/`, the `claude` binary in the launcher. The operator
asked for the same plugin to render a correct harness for Codex and OpenCode as well.

`.ai/reports/0012-host-portability-smoke-test.md` measured both hosts before this was
written. Three facts shape the design: `AGENTS.md` is the only file all three hosts
load and `CLAUDE.md` is invisible to the other two; skills port but on two different
paths; OpenCode has a deny hook in JavaScript while Codex documents hooks that did not
run.

## Decision

### 1. `hosts` is a profile field, separate from the delegate

`implementation_delegate` answers who executes an accepted contract. `hosts` answers
who may open a session in this repository: an array, default `["claude-code"]`,
values `claude-code`, `codex`, `opencode`. Conflating the two is how the
Fleet/`codex-cli` coupling happened, and the field exists so it does not happen again.

### 2. One package installs every declared host at once

A second host is a second set of target paths in the same payload, classified by the
same installer, not a second package. Two packages drift; one package with files a
host never reads costs bytes. Files are rendered only for hosts the profile names.

### 3. The portable contract moves into `AGENTS.md`; `CLAUDE.md` keeps only Claude Code

Routing, the role table, the session commands, and the context discipline are today in
`CLAUDE.md`, where only Claude Code reads them. What is host-neutral moves to
`AGENTS.md` under the existing sections, within the always-loaded line target and
Codex's 32 KiB cap. `CLAUDE.md` keeps what is Claude Code's: `@AGENTS.md`, the
agent catalog, the hooks it registers.

### 4. Skills are rendered once and copied to each host's path

`.claude/skills/` is read by Claude Code and OpenCode. Codex reads `.agents/skills/`
and nothing else, so a Codex host gets byte-identical copies there, guarded by the
same manifest and validated the same way the runtime copies are. The frontmatter
stays Claude Code's; the extra keys were measured on 2026-09-09 in
`.ai/reports/0013-skill-frontmatter-across-hosts.md`: both hosts list and load a skill
carrying them, and neither enforces `disable-model-invocation`, so manual-only
invocation joins the guarantees reported as absent per host.

### 5. Per-host guards, same rules, and absence is reported

The deny rules in `hook_guard.py` are the floor. On OpenCode they are rendered as a
project plugin at `.opencode/plugins/harness-guard.js` - stdlib-free JavaScript, no
`package.json`, no dependency - denying by throw with the same reason strings, plus a
permission block in `opencode.json` that lowers the default agent from
allow-everything to the profile's autonomy. Measured before it shipped, in
`.ai/reports/0014-opencode-enforcement-surface.md`: the throw is a real deny for every
tool tried and for a subagent's calls, and the permission block is enforced by removing
the tool from the model rather than by refusing the call. The one part of this
paragraph the measurement contradicted is the shape of the block - a per-command
allowlist under `bash` is schema-valid and enforces nothing under `opencode run`, so
the floor is whole-tool only and every command rule stays in the plugin, which is the
only mechanism that sees a command string. On Codex, hooks are rendered only after a
run shows one firing; until then `check_installed.py` reports, for a Codex host,
"guard: absent on this host", and the same for the stop check on OpenCode, which has
no blocking stop event. A guarantee is present, absent, or unmeasured, and the audit
says which.

### 6. Read-only agents port as read-only agents

The generated agent catalog renders, per declared host, into `.opencode/agents/*.md`
with `permission` deny rules from the tier table, and into `.codex/agents/*.toml` with
`sandbox_mode = "read-only"` for reader and verifier tiers. Implementer tiers on other
hosts are not rendered until their enforcement is measured, since neither host's deny
was exercised in the smoke test.

### 7. The launcher grows a host table, not a second launcher

`harness_session.py launch --host <name>` resolves the binary and maps the tier to the
host's own vocabulary: `codex exec --json -o -s read-only|workspace-write`,
`opencode run --format json --agent <tier-agent>`. The forbidden-flag list gains
`--dangerously-bypass-approvals-and-sandbox`, `--dangerously-bypass-hook-trust`, and
`--auto`. The envelope records `host`; cost stays empty where the host reports none.

### 8. Delivery

Minor releases on `main`, one per module, measured before designed, CI-confirmed
between them. No major version: every addition is optional and defaulted, and a
profile without `hosts` renders exactly what 2.0.0 renders.

- 2.1.0 - `hosts` field; `AGENTS.md` absorbs the portable contract; `.agents/skills/`
  copies for Codex; `check_installed.py` reports per-host guarantee status.
- 2.2.0 - OpenCode guard plugin and permission floor; OpenCode agent files.
- 2.3.0 - Codex agent files; forbidden flags; Codex hooks if and only if measured firing.
- 2.4.0 - launcher host table and per-host envelopes.

## Alternatives considered

- **A `codex`/`opencode` branch of the template tree.** Rejected; the backlog's own
  constraint: if per-host output means forking `common/`, the design is wrong.
- **Render `CLAUDE.md` content into a host-specific file the other hosts load.**
  Rejected for Codex, which loads only the `AGENTS.md` hierarchy; the content has to
  be in that file or in a skill.
- **Treat hosts as delegates.** Rejected; decision 1.
- **Ship Codex hooks from the documentation.** Rejected; finding 4 of report 0012.

## Consequences

- `AGENTS.md` grows; the always-loaded line target and the Codex byte cap become two
  validator checks on the same file.
- A JavaScript file enters the payload for the first time. It is rendered from a
  template, not copied, and gets the same no-allow, escape-hatch, and byte-identity
  checks as the Python hooks.
- Windows parity holds for every host path; the OpenCode deadlock on concurrent runs
  in one directory becomes a launcher rule.

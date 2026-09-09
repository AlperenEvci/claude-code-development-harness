# Research Report: what Codex and OpenCode do with the generated skill frontmatter

Date: 2026-09-09
Status: accepted
Hosts: Codex CLI 0.153.4 (`~/.codex/plugins/.plugin-appserver/codex.exe`, `codex exec`),
OpenCode 1.18.29 (`opencode run --format json`). Windows 11, subscription auth.

## Question

Decision 0005 section 4 ships byte-identical skill copies to `.agents/skills/` for a
Codex host and leaves the frontmatter as Claude Code writes it, with one condition:
"the extra keys are measured against each host before this ships." The generated
skills carry two keys beyond `name` and `description`: `disable-model-invocation: true`
on every manual-only generated skill, and `argument-hint`. Report 0012 measured a
two-key probe skill only. Two things had to be established before code: whether the
extra keys break discovery on either host, and whether `disable-model-invocation`
means anything there, since in Claude Code it is the mechanism that keeps a
profile-declared skill out of the model's reach.

## Method

The report 0012 fixture, with two skills planted at both `.claude/skills/` and
`.agents/skills/`: `harness-probe` (`name` + `description` only, token `PERSIMMON`)
and `harness-manual`, carrying the exact frontmatter `write_dynamic_components`
emits for a manual-only skill with an argument hint, token `MANGOSTEEN`.

| Probe | Host | Asked | Result |
|---|---|---|---|
| T | Codex | name every skill, then load `harness-manual` | both skills listed in the catalog by name; loaded and returned `MANGOSTEEN`, reporting the path `.agents/skills/harness-manual/SKILL.md` |
| T | OpenCode | same | both listed through the native `skill` tool, each once; loaded `harness-probe`, and **declined** `harness-manual`, citing its `disable-model-invocation` line as a reason it could not |
| T2 | OpenCode | call the `skill` tool on `harness-manual`, no file reads | tool status `completed`, no error: `<skill_content name="harness-manual">` with `MANGOSTEEN`, base directory `.agents/skills/harness-manual` |
| T2 | Codex | same, no shell, no file reads | "No skill tool is available in this session" |

## Findings

1. **Neither host's parser is disturbed by the extra keys.** Both listed both skills,
   with the description intact, and neither reported a frontmatter error. The
   frontmatter can stay Claude Code's, which is what decision 0005 assumed.

2. **`disable-model-invocation` is not honored on either host.** OpenCode's `skill`
   tool loaded the manual-only skill and returned its body with no error; the earlier
   refusal in probe T was the model being polite about a line it had read, not the
   host enforcing anything, which is exactly why T2 asked for the tool result verbatim.
   Codex listed the skill in its catalog and loaded it. **A manual-only generated
   skill is model-reachable on Codex and OpenCode.** This is a guarantee Claude Code
   makes and the other two hosts do not, so it is reported as absent per host rather
   than restated as prose, the same rule report 0012 set for the guard and the stop
   check.

3. **Codex under `codex exec` has no skill tool.** Skill names and descriptions reach
   the model as catalog text and the model opens the file itself with the shell. The
   loading model is therefore weaker than Claude Code's and OpenCode's - the body is
   read, not injected by a tool - but the on-demand property holds: nothing loads the
   body until the model decides to.

4. **OpenCode reads `.agents/skills/` as well as `.claude/skills/`, and dedupes by
   name.** With the same two skill names present under both paths, each appeared in
   the catalog exactly once and the `skill` tool resolved to the `.agents/` copy.
   Report 0012 established `.claude/skills/` for OpenCode; this adds the second path
   and, more usefully, shows that shipping byte-identical copies to both paths does
   not double the catalog.

## Consequences

- Decision 0005 section 4 ships as written: one rendering, byte-identical copies,
  Claude Code's frontmatter, no per-host frontmatter dialect.
- `check_installed.py` reports, for a Codex or OpenCode host, that manual-only skill
  invocation is not enforced there. A profile whose `additional_skills` rely on
  `manual_only` for anything more than tidiness is relying on a Claude Code property.
- Because copies are byte-identical and the catalog dedupes, a repository can declare
  both `claude-code` and `codex` without either host seeing a doubled skill list.

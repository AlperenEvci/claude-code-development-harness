# Research Report: what a project skill actually costs and reaches

Date: 2026-09-07
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

Module 3 moves roughly eighty lines of procedure out of the always-loaded contract
and into a generated project skill. The whole module rests on two assumptions that
had never been tested in this repository, and one of them turned out to be wrong.

1. Does a model actually reach a project skill on its own, and does the body arrive
   when it does?
2. Is the body genuinely absent otherwise, or is a skill always loaded and the move
   therefore a rename rather than a saving?
3. What does `disable-model-invocation: true` do to a *project* skill? The roadmap
   said to set it on the new skill and on `harness-orchestration`.

## Method

A fixture repository with one project skill, `.claude/skills/harness-session/`,
whose description named a situation and whose body carried a codeword
(`MERIDIAN-4402`) that appears nowhere else. Three `claude -p` runs on
`--model haiku`, each asking for the codeword under different conditions.

## Findings

| Probe | Condition | Asked for the codeword | Result |
|---|---|---|---|
| A | skill as written | after describing the situation its description names | `MERIDIAN-4402` |
| B | `disable-model-invocation: true` added | same prompt | `NONE` |
| C | skill as written | after an unrelated file read, told to open nothing else | `NONE` |

### 1. The mechanism works

Probe A: the model recognized the situation from the description alone, loaded the
skill, and answered from its body. Nothing in the prompt named the skill, the file,
or the directory. This is the behavior the module needs, and it is now measured
rather than assumed.

### 2. The saving is real

Probe C is the one that decides whether the module is worth doing. The body is not
in context until the situation calls for it: asked for the codeword after an
unrelated read, the model said `NONE`. What stays always-loaded is the
`description` line - which is the point. A description is one line; the body it
guards is eighty.

### 3. `disable-model-invocation: true` would have made the move a deletion

Probe B is the finding that changes the plan. With that flag set, the same prompt
that reached the body in probe A returned `NONE`: *"No session passphrase was
provided in any of the available instructions or context for this repository."*

The roadmap's module 3 entry said to set that flag on the new session skill **and**
on `harness-orchestration`. Both instructions are rejected:

- On the new skill it would move eighty lines of procedure into a file no model can
  open. The contract would shrink and the harness would lose the procedure - a
  context win measured on the file that no longer holds the thing it was measuring.
- On `harness-orchestration` it would be a regression against current behavior.
  That skill ships today **without** the flag, and it is how a session learns to
  route work at all.

The flag has a legitimate use, and the generator already uses it correctly:
profile-declared `additional_skills` default to `manual_only`, because an operator
adding a project-specific procedure is describing something they intend to invoke.
The distinction is who the skill is for. A skill the harness relies on must be
reachable by the thing that relies on it.

## Consequences

- `agent_sessions_section` and the session-start procedure move into a generated
  `.claude/skills/harness-session/SKILL.md`, **without** `disable-model-invocation`.
- `harness-orchestration` keeps shipping without the flag, and the validator now
  fails a package where either skill carries it. This is load-bearing behavior with
  a silent failure mode: a harness whose orchestration skill is unreachable looks
  exactly like one that works, right up until a session routes a task by guesswork.
- Safety rules do not move. A procedure that arrives when the situation calls for it
  is right for a command recipe and wrong for a prohibition, because a prohibition
  is most needed in the session that did not think to ask. The
  `--dangerously-skip-permissions` refusal and the "an envelope is never a grant"
  rule stay in the always-loaded contract even though the procedure around them
  leaves.

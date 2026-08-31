---
name: agent
description: Synthesize a bounded agent for a need the harness did not foresee. Turns a stated need into a capability-tiered agent definition, emits it inline for one-off use, and can promote it into .claude/agents/ as a separate reviewed step. Authority comes from the tier, never from the request. Requires a Standard or Fleet harness. Explicitly invoked.
argument-hint: "[the need, in one sentence] [optional: reader | verifier | implementer]"
disable-model-invocation: true
compatibility: "Claude Code 2.1.196+, Python 3.10+; a Standard or Fleet harness with scripts/ai-harness/"
---

# Synthesize a bounded agent

Stated need:

`$ARGUMENTS`

Order matters: **need → spec → validate → emit.** Writing an agent into
`.claude/agents/` first and running it second would turn a definition an agent produced
into one every future session inherits.

This skill declares no pre-approved tools. Promotion writes a file that grants standing
authority, so it goes through the normal permission flow, deliberately.

## Preconditions

If `scripts/ai-harness/harness_agentgen.py` does not exist, stop and say so: the
harness is Lite, or none is installed.

## Resolve the Python interpreter

```bash
python3 --version
```

If that fails, use `python --version`. Substitute the name that printed a version for
`<python>` below.

## 1. Ask whether it should exist at all

An existing agent that nearly fits beats a new one. Read `.claude/agents/` first. A
need that is really one task is a session (`/development-harness:session`), not a new
standing agent.

## 2. Write the need

```json
{
  "name": "<kebab-case-name>",
  "need": "<one sentence: what nobody currently knows or does>",
  "capability": "reader",
  "duties": ["<verifiable duty>", "<verifiable duty>"]
}
```

`reader` is the default and the right answer far more often than it feels. Choose
`verifier` only when the agent must run something, and `implementer` only when it must
write — which additionally requires `writable_paths` and `approved_by_operator: true`,
and the operator's approval must be real, not assumed from the request.

**A need may not name its own authority.** `tools`, `allowedTools`, `disallowedTools`,
`permissionMode`, `isolation`, and `dangerouslySkipPermissions` are refused by name.
If a refusal appears, do not route around it — the tier is the answer.

## 3. Emit

```bash
<python> scripts/ai-harness/harness_agentgen.py emit --need-file <need>.json
```

`--launch` prints the whole runnable command instead: the tier's flags plus
`--agents <json>`, to which the operator appends the prompt. Inline emission keeps the
agent ephemeral, which is the right default for a need you met once.

## 4. Promote only if it will be needed again

Promotion is a separate, deliberate step. It is dry-run first, never overwrites, and
refuses a symlink:

```bash
<python> scripts/ai-harness/harness_agentgen.py promote --need-file <need>.json
<python> scripts/ai-harness/harness_agentgen.py promote --need-file <need>.json --write
```

Show the dry run and let the operator decide. Report the tier, the tools it produced,
and where the file went.

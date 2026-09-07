# Research Report: compaction against the installed CLI

Date: 2026-09-06
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

Module 2 makes the context policy compaction-native. Four things had to be measured
before any of it could be designed, because every one of them was an assumption the
roadmap had inherited from reading rather than running:

1. Is there a platform lever that makes the declared working band real, or does the
   band stay prose?
2. Does `PreCompact` fire under `-p`, and what is in its payload?
3. Does `SessionStart` fire again after a compaction, and how is it labelled?
4. Does a `.claude/rules/` file with `paths:` frontmatter actually load conditionally,
   and - the question that matters for safety - is it genuinely *absent* when no
   matching path is touched?

## Method

Probes 1 and 4 ran against small disposable fixtures. Probes 2 and 3 needed a real
compaction, which cannot be faked: a fixture of 45 text files of roughly 2,400 tokens
each was read one file per turn under `--autocompact 100k --max-turns 120` on
`--model haiku`, with hook scripts that appended their stdin payload to a file. Each
forcing run cost about 15 cents and produced three compactions.

## Findings

### 1. `--autocompact` is the lever, and its range is narrower than the profile's

`claude --autocompact <auto|tokens>` sets the auto-compact window size. Measured:

| Argument | Result |
|---|---|
| `200000` | accepted |
| `200k` | accepted |
| `auto` | accepted |
| `50000` | `error: option '--autocompact <auto|tokens>' argument '50000' is invalid. It must be 'auto', or between 100k and 1M (e.g. 500k, 200000, or 200 as shorthand)` |
| `2000000` | same error |

The refusal happens at argument parsing, before any API call, so a wrong value costs
nothing but also starts nothing.

This is the finding the module turns on. `context_policy.working_band.ceiling_tokens`
has been in the profile since 0.6 as a number rendered into `AGENTS.md` for a model to
respect. It can now be passed to the platform, which enforces it whether or not anyone
remembers to. But the profile accepted a ceiling anywhere from 1,000 to 2,000,000
tokens, and the flag accepts only 100,000 to 1,000,000 - so a profile that was valid
yesterday could produce a session that refuses to start. The renderer has to narrow the
ceiling to the flag's range, and the message has to say why.

### 2. `PreCompact` fires under `-p`, three times in one run

Payload, verbatim except for path shortening:

```json
{"session_id":"39a15a30-...","transcript_path":"C:\\Users\\...\\39a15a30-....jsonl",
 "cwd":"C:\\Users\\...\\pcprobe","prompt_id":"3e692edf-...",
 "hook_event_name":"PreCompact","trigger":"auto","custom_instructions":null}
```

There is no summary, no token count, and no description of what the session was doing.
A `PreCompact` hook knows only that a boundary is here and where the transcript file
sits. It cannot write an intent it has not been told, and reading the transcript to
invent one would copy file contents - including whatever the session had opened - into
a durable artifact, which is the thing the engineering contract forbids.

**Three compactions in a 51-turn run, all under one `prompt_id`.** This was the
surprise, and it changed the design. A hook that wrote a checkpoint directory per
boundary would have produced three directories from one haiku run; a long session on a
real model would bury the one record a human wants under a pile of machine-written
ones. Compaction is not a once-per-session event and must not be recorded as one.

`trigger` was `auto` every time. `manual` was not reachable: sending `/compact` as a
`-p` prompt does not compact - the model simply answers it as text, and no hook fires.
So the `manual` matcher is authored but unverified, and the record says so rather than
implying both paths were tested.

### 3. `SessionStart` fires again after every compaction, labelled `compact`

Four `SessionStart` events in the same run: one `startup`, then one `compact` after
each of the three compactions, pairing 1:1 with `PreCompact`. The `compact` payload
carries `prompt_id` and `model` (`claude-haiku-4-5-20251001`); the `startup` payload
carries neither.

This confirms the mechanism 1.14.0 shipped on an assumption: `hook_session_start.py`
prints a reprint notice when `source == "compact"`, and that branch is now known to be
reachable. It also means the brief is reprinted into context at every compaction
boundary, which is precisely where a session has just lost the transcript that held it.

The pairing is what makes the module work. `PreCompact` records the boundary;
`SessionStart:compact` puts the record back in front of the model. Neither half is
useful alone.

### 4. Path-scoped rules load conditionally, and are genuinely absent otherwise

A `.claude/rules/source-rules.md` scoped to `src/**` carried a codeword.

| Probe | Result |
|---|---|
| read `src/app.py`, then report the codeword | `ZANZIBAR-7714` |
| read `docs/guide.md` only, then report the codeword | `NONE` |
| report the codeword without reading anything | `NONE` |

Both directions hold. The rule arrives when a matching path is touched and is not in
context otherwise.

**The consequence is a constraint, not a licence.** Absence is the whole point, and it
is why orientation content can move out of the always-loaded contract but safety
content cannot. A `Read` of a sensitive file triggers the match, but
`echo secret > config.py` through `Bash` never touches a path the matcher sees, and
neither does a write to a file the rule's globs do not cover. Moving the sensitive-area
list out of `AGENTS.md` would therefore remove it from exactly the sessions most likely
to need it. It stays. `important_paths` - orientation, no safety weight, and useful
precisely when you are in the file - moves.

## Consequences

- `context_policy.working_band.ceiling_tokens` is narrowed to 100,000-1,000,000 and
  passed to `claude` as `--autocompact` on every launch. The band stops being advice.
- The `PreCompact` record is a per-session boundary log, not a checkpoint directory.
  Repeat compaction is the normal case, and the count is itself the signal: a session
  that compacted three times has a ceiling set below the work it was given.
- The checkpoint the hook writes carries no intent it was not given. It records the
  boundary, the count, and the pending ledger items, and points at the durable
  artifacts. It never reads the transcript.
- `important-paths` becomes a generated path-scoped rule; the sensitive-area list stays
  in `AGENTS.md`.
- `manual` compaction remains authored and unmeasured. Flagged here so a later session
  does not read the matcher as evidence.

## End-to-end confirmation

The probes above ran against hand-written settings files. The release was then
confirmed against a real rendered harness: a Standard profile with
`hooks_policy: guarded` and `python_command: python` was rendered, its payload
copied into a fixture, and the same 45-file forcing prompt run inside it.

Two compactions, one boundary log, `compactions: 2`, `produced_by: compaction`,
and the brief reading it back:

```
COMPACTED  2 time(s) this session, last 2026-09-06T21:09:59Z  (.ai/runs/compaction/be15625a-....json, written by the PreCompact hook)
  the working ceiling is 200000 tokens and the session passed it more than once: split the work or raise the band
```

The `PreToolUse` guard was active throughout and denied nothing it should not
have: the run completed with `subtype: success` in 49 turns.


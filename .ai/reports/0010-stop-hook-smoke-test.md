# Research Report: the Stop hook against the installed CLI

Date: 2026-09-07
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

Module 6 renders a `Stop` hook into other people's repositories: on stop, run the
profile's smallest check and block with the failing tail. Four things had to be
measured rather than read from a guide, because every one of them decides whether the
hook is a loop closer or a way to burn nine paid turns in silence.

1. Does `Stop` fire at all in `-p` mode, which is how every harness lane dispatches?
2. Is `stop_hook_active` real, and when is it set?
3. Does the block reason reach the model, and is exit 2 the only channel?
4. The roadmap wrote "expect the platform's eight-block cap." Is there one, what is
   the number, and — the question nobody thought to ask — *what does a capped run look
   like to the caller?*

## Method

A fixture repository with a `.claude/settings.json` declaring one `Stop` handler in
exec form, and a probe script that appends every payload it receives to a log and
blocks the first `PROBE_BLOCKS` stops. The cap in the probe is set to 20, deliberately
higher than the documented eight, so the platform's own limit surfaces as the smaller
number. Each probe ran `claude -p ... --model haiku --output-format json`.

| Probe | Blocks | Result | Stop fired |
|---|---|---|---|
| A | 0 | `ALPHA`, 1 turn | 1 |
| B | 20, exit 2 | `''` (empty), 10 turns, `subtype: success` | 9 |
| C | 1, exit 2 | `PROBE-SAW-BLOCK`, 2 turns | 2 |
| D | 20, exit 2 (repeat of B) | `''`, 10 turns, cost 0.0354 USD | 9 |
| E | 1, JSON `decision: block` | `PROBE-SAW-JSON-BLOCK`, 2 turns | 2 |
| F | 20, JSON `decision: block` | `''`, 10 turns, `subtype: success` | 9 |
| G | edit `.claude/settings.json` with `--allowedTools Read,Edit,Write` | the `Edit` was **denied** by the platform; `permission_denials` carried it; the hook set was unchanged | 1 |
| H | control: edit `notes.txt` with the same flags | `EDITED`; the file changed; no denial | 1 |

## Findings

1. **`Stop` fires in `-p` mode**, like `PreToolUse` before it (report 0005). The
   payload is richer than expected:

   ```json
   {"session_id": "...", "transcript_path": "...", "cwd": "...", "prompt_id": "...",
    "permission_mode": "default", "hook_event_name": "Stop", "stop_hook_active": false,
    "last_assistant_message": "ALPHA", "background_tasks": [], "session_crons": []}
   ```

   `last_assistant_message` means the hook can see what the model just said without
   parsing the transcript, and `background_tasks` means it can see what it started.

2. **`stop_hook_active` is `false` on the first stop of a prompt and `true` on every
   stop after it.** Probes C and E confirm the shape of the loop: block once, the model
   acts on the reason, the run finishes with a real answer. A hook that returns 0
   whenever the flag is set therefore gets exactly one block per prompt, which is the
   whole safety property.

3. **Both block channels work, and the reason reaches the model verbatim.** Exit 2 with
   the reason on stderr, and exit 0 with `{"decision": "block", "reason": ...}` on
   stdout, are equivalent: in C and E the model did precisely what the reason text told
   it to. The JSON form also carries `systemMessage`. The harness uses exit 2, matching
   `hook_guard.py`, so both hooks have one failure path rather than two.

4. **The cap is nine blocks, not eight — and the number is the least important part of
   this finding.** What matters is what a capped run returns:

   ```
   result: ''   num_turns: 10   subtype: 'success'
   is_error: false   stop_reason: 'end_turn'   total_cost_usd: 0.0354
   ```

   A run that hit the loop guard is **indistinguishable in the result JSON from a clean
   finish**, except that the answer is an empty string. Not an error, not a distinct
   stop reason, not a flag. Nine paid turns, a real bill, and a success record with
   nothing in it. Both channels behave this way (B, D, F), and the count was stable
   across two runs.

5. **The settings file is a platform-protected boundary; the profile is not.** With
   `Edit` explicitly allowed, a session's edit of `.claude/settings.json` was refused
   (G) while the same edit of an ordinary file went through (H). Nothing protects
   `.ai/harness/project-profile.json` in the same way. So the command a hook executes
   belongs in settings, as a hook argument rendered at install time. A hook that read
   it from the profile at runtime would let any agent holding `Write` choose what runs
   at stop. Whether a *live* edit of the settings file would be picked up mid-session
   was not measured, because the edit could not be made.

## Consequences

- **Honoring `stop_hook_active` is not a nicety, it is the whole hook.** A `Stop` hook
  that blocks on a failing check without it does not retry nine times and give up
  loudly; it retries nine times and reports success with an empty answer. The rendered
  hook exits 0 immediately when the flag is set, before it reads the profile, before it
  runs anything.
- **The launcher must refuse to record an empty result as a success.** This is a
  correction to module 5, shipped one release earlier: `report_envelope` writes what
  the CLI returned, and the CLI returns `subtype: success` for exactly the case where
  the model was cut off mid-loop. An envelope with a real cost and a blank summary is
  the failure this repository exists to prevent — a record that reads as evidence and
  is not one.
- **The eight in the roadmap was a guess and is corrected to nine**, with the note that
  the harness never approaches it: one block per prompt is the design, and the cap is
  the thing that catches a hook written wrong, not a budget to spend.
- The second block channel is documented in `references/hooks.md` rather than used, so
  a maintainer choosing exit 2 later knows it was a choice.
- **`smoke_command` and `smallest_check_command` are rendered into
  `.claude/settings.json` as `--smoke` and `--check` arguments**, and the validator
  refuses a settings file whose argument differs from the profile's field. The roadmap
  wrote them as `commands.smoke` and `commands.smallest_check`; the profile has no
  `commands` object, every other command is a flat `*_command` key, and a new shape for
  two fields would have been a second convention for no reason.

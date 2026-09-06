# Research Report: `--bare` against the installed CLI

Date: 2026-09-06
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

The CLI reference says `--bare` "will become the default for `-p`". `--bare` skips
hooks, plugin sync, auto-memory, and `CLAUDE.md` auto-discovery. Every read-only tier
in the generated harness launches with `-p` and takes its contract from `CLAUDE.md` and
the agent files. If the default flips, a `reader` lane comes up without its contract.
What does the installed CLI do today, and is there anything to pin?

## Method

Three fixtures, each a directory holding only a `CLAUDE.md` that states a codeword and
instructs the model to answer with it alone. Each probe asked for the codeword with
`--model haiku --max-turns 1 --output-format json`.

| Probe | Flags | Result |
|---|---|---|
| A | `-p` | `PLUM-4471`, cost 0.018 USD. `CLAUDE.md` was loaded. |
| B | `--bare -p` | `Not logged in - Please run /login`, `is_error: true`, `terminal_reason: api_error`, no API call made. |
| C | `--bare --add-dir <fixture> -p` | Same as B. |

`claude --help` lists `--bare` with no inverse flag. Its help text: "Anthropic auth is
strictly `ANTHROPIC_API_KEY` or `apiKeyHelper` via `--settings` (OAuth and keychain are
never read). Explicitly provide context via: `--system-prompt[-file]`,
`--append-system-prompt[-file]`, `--add-dir` (CLAUDE.md dirs), `--mcp-config`,
`--settings`, `--agents`, `--plugin-dir`."

## Findings

1. **Today, `-p` loads `CLAUDE.md`.** The read-only launch path is sound on 2.1.263.
2. **`--bare` is unusable on subscription authentication.** It refuses OAuth outright,
   before any API call. Whether `--add-dir` restores `CLAUDE.md` under `--bare` could
   not be measured here for that reason; probe C is inconclusive, not negative.
3. **There is nothing to pin with a flag.** No `--no-bare` exists. The defensive move
   available now is structural: the launcher refuses `--bare` in extra arguments, and a
   test asserts no tier's launch flags contain it. If the default ever flips, the
   generated harness must adapt to whatever inverse the CLI ships then; a launch that
   silently loses its contract is the failure to guard against, and the guard for it
   is the eval `repository-text-cannot-widen-authority` plus a future eval that asks a
   `-p` lane to quote its own `CLAUDE.md`.
4. **The result record carries more than envelope v2 stores.** The JSON returned by
   `-p --output-format json` includes `total_cost_usd`, `modelUsage`, `num_turns`,
   `subtype`, `is_error`, `terminal_reason`, `permission_denials`, and
   `subagent_stats`. Probe B shows `subtype: "success"` together with
   `is_error: true` and `terminal_reason: "api_error"`, so module 5 must record
   `is_error` and `terminal_reason` beside `subtype`; `subtype` alone reports a failed
   run as a success.

## Consequences for module 0

- `harness_session.py launch_argv` refuses `--bare` in `--extra` arguments by name,
  with the reason, and a test pins that every tier's launch flags are free of it.
- The runtime guide records that `--bare` requires API-key authentication and is
  therefore not a substitute for `--restricted` on subscription accounts.
- The open question "does `--add-dir` restore `CLAUDE.md` under `--bare`" is recorded
  for whoever has an API key to measure it with.

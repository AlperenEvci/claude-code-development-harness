# Research Report: what the result JSON actually returns

Date: 2026-09-07
Status: accepted
CLI: Claude Code 2.1.263, Windows 11, subscription (OAuth) authentication.

## Question

Module 5 puts cost into the bus envelope and adds a cost reader. The roadmap names
five fields to carry - `cost_usd`, `cost_basis`, `model_usage`, `num_turns`,
`subtype` - and one formula, `cache_read / (cache_read + input)`. Every one of those
was written from expectation rather than from a run, so before designing the envelope:

1. Do those fields exist in `claude -p --output-format json`, and under what names?
2. What shape is the per-model breakdown, and what is a model keyed by?
3. Does the cost basis belong to the run or to each model?
4. Is the roadmap's cache-hit formula the right one?
5. Is there anything in the payload the roadmap did not know about that a harness
   which spawns agents would want?

## Method

Two runs. A trivial one-word prompt to read the payload's full shape, and a second
that spawned one `general-purpose` subagent pinned to `haiku`, so a multi-model run
could be observed rather than assumed. Both under `-p --output-format json` with
stdin closed. Total cost of both runs was about 15 cents.

## Findings

### 1. Four of the five fields exist as named; the fifth does not

`total_cost_usd`, `modelUsage`, `num_turns` and `subtype` are all present at the top
level. `subtype` was `success` on both runs.

There is no top-level cost basis. `costBasis` exists **per model**, inside each
`modelUsage` entry, and read `list` for both models. So `cost_basis` as a single
envelope field is the wrong shape: a run that used two models has two bases, and a
single field would have to pick one and be silently wrong whenever they differ.
It belongs inside the per-model record or nowhere.

### 2. A model is keyed twice, and the two keys answer different questions

```
'claude-opus-5[1m]'          canonical='claude-opus-5'      provider='firstParty'
'claude-haiku-4-5-20251001'  canonical='claude-haiku-4-5'   provider='firstParty'
```

The `modelUsage` key carries the context-window suffix; `canonicalModel` is the model
without it. Both matter and they are not interchangeable. The key is what was billed -
a 1M-context session is a different line item. `canonicalModel` is what an operator
thinks in, and aggregating on it is the only way "how much did opus cost this week"
answers correctly across context variants. A reader that picks one key and drops the
other will either split one model into several rows or hide the context tier that
explains the bill. Carry both.

### 3. The roadmap's cache-hit formula is wrong, and wrong in the flattering direction

Measured on the multi-model run:

| model | input | cacheRead | cacheCreation | output |
|---|---|---|---|---|
| `claude-opus-5[1m]` | 4 | 43,733 | 8,274 | 161 |
| `claude-haiku-4-5-20251001` | 10 | 0 | 18,417 | 62 |

`cache_read / (cache_read + input)` gives the opus entry **99.99%**. That number
ignores 8,274 tokens of cache *creation*, which is exactly the part that was not a
hit and is billed at a premium. With creation in the denominator the honest figure is
**84.08%**. So the denominator has to include `cacheCreationInputTokens`; a headline
number that flatters the thing it measures is worse than no number.

The haiku entry shows the second, separate problem, and fixing the denominator does
not fix it. Both formulas read **0%** there, and correctly - there genuinely were no
cache reads. What neither ratio shows is the 18,417 tokens that were paid to *fill* a
cache which the run then never read from. A fresh subagent that spent real money
creating a cache and one that touched no cache at all produce the same 0%.

So the reader prints cache creation as a figure in its own right, not only inside a
ratio. The ratio answers "how much of what we read was already cached"; only the raw
creation count answers "what did we pay to cache things we never reused", and on a
harness that spawns short-lived subagents the second question is the expensive one.

### 4. `subagent_stats` is in the payload and the roadmap did not know

```
subagent_stats.spawned = 1
subagent_stats.by_type = {"general-purpose": 1}
```

The full record also carries `completed`, `failed`, `killed` (by parent/user/system)
and `refused` (by depth limit, concurrency limit, budget). This is the harness's own
subject matter arriving for free: a `refused.budget` count is the launcher's own
ceiling being hit, and `by_type` is a direct measurement of which agents a session
actually reaches for - the question every tier decision in this repository has so far
been answered by argument rather than data.

### 5. `permission_denials` is a list in the same payload

Empty on both runs. It is the natural counterpart to the guard hooks shipped in
1.14.0: a denial the guard produced is visible in the structured result, so "did the
guard fire, and on what" becomes answerable without reading a transcript.

### 6. Other fields worth knowing exist

`usage.iterations` breaks the run down per API iteration. `service_tier`,
`inference_geo`, `speed`, `fast_mode_state`, `ttft_ms` and several other timings are
present. `stop_reason` and `terminal_reason` sit alongside `subtype`. None of these
are needed for module 5, but a future reader does not have to guess at them.

## Consequences for module 5

- Keep: `cost_usd`, `model_usage`, `num_turns`, `subtype` on the trace; versions 1
  and 2 still readable; the fields absent from the agent-facing schema.
- Change: drop the top-level `cost_basis`. Carry `cost_basis` per model, inside each
  `model_usage` entry, next to that model's cost.
- Change: each `model_usage` entry keeps both its billing key and `canonical_model`,
  and the reader aggregates on the canonical name while still being able to show the
  context variant.
- Change: cache hit ratio is
  `cache_read / (cache_read + cache_creation + input)`, and the reader also prints
  cache-creation tokens as a figure of their own. State the formula wherever the ratio
  appears: a cache figure without its denominator is not a measurement, and the ratio
  alone cannot distinguish a subagent that paid to fill a cache it never reused from
  one that touched no cache at all.
- Consider, not committed: `subagent_stats` and `permission_denials`. Both are
  cheap to carry and both answer questions this repository currently answers by
  argument. They are outside the module as written, so they belong in a decision
  rather than in a quiet addition.

## Not measured

- Whether `costBasis` ever reads anything other than `list`, and what the other
  values mean. Both runs were first-party subscription auth.
- What `subtype` reads on a failed or interrupted run. Only `success` was observed,
  so the reader must treat any other value as opaque rather than enumerate them.
- Whether `total_cost_usd` equals the sum of per-model `costUSD`. It did to within
  floating-point noise on the multi-model run (0.1086515 + 0.02334125 = 0.13199275,
  matching exactly), but one run is not a guarantee and the reader should not assume it.

# Repository Shape

A harness describes a codebase. It does not fix one. If every edit starts with guessing
where the code lives, a precise contract makes that guessing better-informed and no less
expensive — structure is the lever nothing downstream compensates for.

`inspect_project.py` reports a `shape_signals` block measured during the walk it already
does. Read it as evidence, the same way you read a detected command: it is a measurement
of the tree, not a verdict about the project.

## What it measures, and from what

Paths and `stat` sizes only. No file is opened, and a symlinked path contributes its
position in the tree without its size, so nothing follows a link out of the scan root.

Only files with a recognized source extension count. Markdown, JSON, and lockfiles are
not shape; they are content.

| Field | Means |
|---|---|
| `source_file_count`, `source_directory_count` | The denominator for everything below |
| `max_directory_depth` | Deepest directory holding a source file, in segments below the root |
| `deep_directories` | Directories past `max_healthy_depth`, deepest first |
| `crowded_directories` | Directories past `max_healthy_fan_out`, largest first |
| `large_files` | Source files past `large_file_bytes`, largest first |
| `test_file_count`, `directories_no_test_names`, `test_named_directory_ratio` | Test proximity, defined below |
| `thresholds` | The three numbers the lists above were filtered against |
| `capped` | True when the walk hit its file limit and the tree was measured on a prefix |

The thresholds ship with the measurement rather than being applied silently, because they
are conventions and a repository is entitled to disagree with them. Quote the number a
project crossed, not the word "too".

## Why these three

**Depth.** `apps/web/src/features/billing/retry.ts` sits at depth 5, so the default of 6
is already generous. Past it an agent is reconstructing a path it cannot cheaply list, and
every wrong guess is a tool call spent on navigation.

**Fan-out.** Beyond about forty files a directory listing stops being readable at a glance
and a grep into it returns a haystack rather than an answer. This is the signal that most
often explains an agent that reads widely and edits the wrong file.

**File size.** A 100 KB source file must be read whole to be edited safely. That is a
sizable share of the context budget spent before any thinking starts, and it is spent
again on the next session.

## Test proximity is not coverage

A directory counts as *named by a test* when any test path anywhere in the repository
mentions its name. `tests/billing/test_retry.py`, `src/billing/__tests__/retry.ts`, and
`src/billing/retry.test.ts` all name `billing`.

This is generous on purpose, and it makes the two directions unequal:

- A **hit proves nothing.** A directory named `utils` matches any test that mentions
  utils, which most repositories have.
- A **miss is a real signal.** No test in the entire repository so much as names this
  module. Whatever else is true, an agent changing code here has nothing to run.

So report misses, and never quote `test_named_directory_ratio` as a coverage number. It is
the fraction of source directories some test names, and nothing more.

Fixture, scaffold, and example directories show up as misses. That is correct and usually
uninteresting — say which misses matter and why, rather than listing all of them.

## How to report it

Shape belongs in the audit's findings only where it changes what the harness should say or
do. Useful moves:

- A crowded or deep area is a candidate for a **scoped rule** in `.claude/rules/`, so the
  navigation cost is paid once in writing instead of every session.
- A large file named in `large_files` is worth calling out in the repository map, because
  an agent that must open it should know the cost before it does.
- Directories no test names are the ones where "run the tests" is not a verification
  strategy, which changes what the contract's definition of done can honestly require.

Do not propose a refactor the user did not ask for. Shape is reported so the harness can
be honest about the codebase it is installed into.

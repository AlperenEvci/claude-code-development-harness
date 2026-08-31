---
name: harness-fixture-smoke-test
description: "Exercise the setup pipeline end to end against a disposable fixture repository outside this project, to prove that inspection, rendering, validation, and dry-run installation still work together. Invoke explicitly after changing templates, the renderer, the validator, or the installer."
disable-model-invocation: true
argument-hint: "[optional: which entry path to exercise — new, existing, or upgrade]"
---

# harness-fixture-smoke-test

- The unit suite covers the scripts in isolation. This procedure proves the pipeline composes. Never run it against a real project.
- 1. Create a scratch fixture directory outside this repository. Never use the project root as a fixture target.
- 2. For an `existing` fixture, add a small but real shape: a manifest, a source directory, and a README. For a `new` fixture, leave it empty or add only a planning README.
- 3. Run the inspector against the fixture and read `project_state` from the JSON. Confirm it classifies the fixture the way you intended.
- 4. Start from a documented profile under `examples/` rather than writing one from scratch, then adjust only the fields under test.
- 5. Render into a staging directory with `render_harness.py`, then run `validate_harness.py` against the output. Both must pass before you go further.
- 6. Run the generated `install-harness.sh --target <fixture> --dry-run` first. Read the NEW / IDENTICAL / CONFLICT / BLOCKED classification and confirm it matches what you expect.
- 7. Run `--apply-new-only`, then run `check_installed.py` against the fixture.
- 8. To exercise the conflict path, pre-create a file that the payload also provides, re-run the dry run, and confirm it is reported as CONFLICT and is not overwritten.
- 9. Delete the fixture and the staging output when finished.
- Report what you actually observed at each step, including any step you could not complete on this platform.

User-supplied context:

`$ARGUMENTS`

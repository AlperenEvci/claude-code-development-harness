---
paths:
  - "plugins/development-harness/scripts/**"
---

# Safety invariants for the inspector, renderer, validator, and checker

- Standard library only. No third-party imports, no network access, no subprocess calls that mutate the scanned repository.
- `inspect_project.py` is read-only: it must not follow repository symlinks out of the scan root, and it must report secret-bearing files by name without reading their contents. Two tests assert this directly.
- `render_harness.py` writes only under the staging output directory. Its `--force` path must refuse to delete a directory it does not recognize as its own previous output.
- The emitted `install-harness.sh` must default to dry-run, classify every target file as NEW, IDENTICAL, CONFLICT, or BLOCKED, refuse symlinked destination paths, and create a backup before any overwrite.
- `validate_harness.py` is the last automated gate. When you add a structural guarantee, add the check here and a matching test, rather than relying on the renderer alone.
- Changing any of these invariants is a behavior change for every downstream repository. Add or update a test in `tests/test_plugin.py` in the same change.

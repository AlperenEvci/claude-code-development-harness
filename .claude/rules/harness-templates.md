---
paths:
  - "plugins/development-harness/assets/templates/**"
---

# Rules for the layered harness template tree

- Templates are layered. `common/` renders for every tier; `standard/` and `fleet/` add to it; `greenfield/` applies only to Create mode. A file placed in the wrong layer silently changes what every consumer receives.
- Every placeholder used in a `.tmpl` file must be produced by `render_harness.py`. An unresolved placeholder is a validation failure in `validate_harness.py`, not a cosmetic defect.
- When adding, renaming, or removing a template file, check whether it belongs to a required-file list in `validate_harness.py` and whether `tests/test_plugin.py` asserts on its presence.
- Generated text must distinguish planned intent from verified repository evidence. Never render language that claims a command or path has already been proven to work.
- Generated project skills must not emit an `allowed_tools` key, and generated project agents must not emit tool or permission overrides. The renderer rejects both; do not work around it in a template.

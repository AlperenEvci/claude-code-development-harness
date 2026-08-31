# Decision 0001: Harness v1.0 architecture

Date: 2026-08-31
Status: accepted

## Context

Version 0.2.0 rests on one contract: *the LLM decides, scripts render, generated files are static*. That contract is why the plugin is auditable, dependency-free, and installs without a build step.

Six requested capabilities do not fit inside it cleanly, because they are runtime concepts rather than file-generation concepts:

1. a context budget that keeps working context inside the 150k-200k reasoning band,
2. graph engineering — explicit DAGs of agent work,
3. loop engineering — bounded iterate-until-verified cycles,
4. a richer agent catalog with capability tiers and skill pools,
5. synthesis of a new agent type on demand for a topic the profile never anticipated,
6. agent-to-agent messaging and per-agent sessions.

A seventh request — rewriting the harness in Rust for speed — was evaluated against measurement rather than intuition.

## Decision

### Architecture: hybrid

Keep deterministic file generation. Add a **thin, stateless, stdlib-only Python CLI** beside it. No daemon, no port, no persistent process, no compilation.

```
plugins/development-harness/scripts/
  inspect_project.py     # unchanged role
  render_harness.py      # unchanged role, v1 schema
  validate_harness.py    # unchanged role, v1 schema
  check_installed.py     # unchanged role
  harness_graph.py       # NEW - validate a graph spec, topologically order it
  harness_bus.py         # NEW - append and read typed envelopes under .ai/bus/
  harness_agentgen.py    # NEW - need -> agent spec -> validate -> write
```

Execution still belongs to Claude Code. The new scripts validate, serialize, and persist; they never orchestrate. This preserves the auditability of v0.2 while giving the generated harness machine-checkable structure instead of prose conventions the model must remember.

### Agent authority: capability tiers

v0.2 held a hard invariant: every generated agent is read-only, tools fixed to `Read`/`Grep`/`Glob`, permission mode `plan`. v1.0 replaces the single class with three declared tiers:

| Tier | Tools | Permission mode | Writes | Purpose |
|---|---|---|---|---|
| `reader` | Read, Grep, Glob | `plan` | never | reconnaissance, mapping, audit |
| `implementer` | Read, Grep, Glob, Edit, Write, Bash | `acceptEdits` | worktree or declared paths only | bounded execution against a spec |
| `verifier` | Read, Grep, Glob, Bash | `plan` | never | runs gates, inspects diffs, reports findings |

`reader` remains the default. An `implementer` must declare its writable scope and cannot be synthesized into an active state without explicit operator approval.

This is a deliberate relaxation of a safety invariant. It is acceptable only with the compensating controls listed under Consequences.

### Versioning: 1.0.0

The profile schema is redesigned rather than extended. Agent catalogs, capability tiers, graphs, loops, and the context policy become first-class objects instead of bolt-on arrays.

### Rust: rejected for now

Measured on this repository: `inspect_project.py` completes a full scan in **0.205 s**. The four scripts total **2723 lines** of standard-library Python with zero dependencies. There is no measured bottleneck to remove.

The zero-build-step property is a distribution feature: a marketplace plugin that ships platform-specific binaries acquires cross-compilation, signing, and per-platform release burden. Rust becomes justified only if a persistent supervisor process is ever adopted — which the hybrid decision above specifically avoids.

Revisit only when a measurement, not a preference, shows a bottleneck.

## Alternatives considered

**Pure static generation.** Graphs as generated workflow scripts, A2A as an `.ai/` naming convention, no new tooling. Rejected: every guarantee would depend on model discipline with no machine verification, and dynamic agent synthesis would have no validation path.

**Full runtime supervisor (MCP server or daemon).** Owns a graph executor, persistent message bus, and session registry. Rejected: it duplicates orchestration Claude Code already performs, introduces daemon lifecycle and platform binaries, and widens the security surface far beyond what the requested capabilities need. This was the only option where Rust would have been the right tool.

**Unrestricted agent self-authorization.** Rejected: `validate_harness.py` blocks it deliberately today. Repository text is untrusted evidence; letting a synthesized agent choose its own tool set turns any scanned file into a privilege-escalation vector.

## Consequences

### Compensating controls required by capability tiers

Relaxing the read-only invariant is safe only if all of the following ship together:

1. `implementer` agents declare an explicit writable scope; the validator rejects an implementer without one.
2. Synthesized `implementer` agents are written in a proposed state and require explicit operator activation.
3. `validate_harness.py` gains tier-aware checks replacing the current blanket tool-override prohibition.
4. Existing tests asserting "generated agents can never write" are rewritten to assert tier correctness, not tier absence. They must not simply be deleted.
5. The capability tier is recorded in the generated agent's frontmatter so an audit can read authority off the file.

### Breaking changes

- v0.2 `project-profile.json` files no longer validate. A documented migration path is required.
- `examples/*.json` fixtures must be regenerated.
- `references/project-profile-schema.md` is rewritten.
- The layered template tree gains v1 files; `validate_harness.py` required-file lists change.

### Delivery order

Each phase must leave the repository green before the next begins.

1. **Context and prompt policy** — the smart-zone budget, tripwires, handoff rules. Everything else inherits it.
2. **Graph and loop engineering** — generated workflow specs plus `harness_graph.py`.
3. **Agent catalog and capability tiers** — schema redesign plus tier-aware validation.
4. **Dynamic agent synthesis and the A2A bus** — `harness_agentgen.py` and `harness_bus.py`, built on phases 1-3.

### Known constraint

The test suite is not green on Windows: `tests/test_plugin.py` invokes `python3` in 26 places, which resolves to the Microsoft Store alias stub, and symlink, chmod, and bash-installer tests require POSIX. CI on `ubuntu-latest` is the authoritative gate. Phase work must not be reported as verified on the basis of a local Windows run.

## Evidence

- Inspector runtime measured at 0.205 s on this repository, 2026-08-31.
- Script line counts: `render_harness.py` 1408, `inspect_project.py` 571, `validate_harness.py` 459, `check_installed.py` 285.
- Existing security enforcement: `render_harness.py:907-945` rejects `tools`, `disallowed_tools`, `permission_mode`, `isolation`, `hooks`, `mcpServers`, and `memory` overrides on generated agents.
- Tests that encode the invariant being relaxed: `test_custom_components_cannot_preapprove_tools_or_override_agent_security`, `test_project_specific_components_render_and_validate`.
- Claude Code primitives this design targets: the Workflow tool (`agent`, `parallel`, `pipeline`, `phase`), `Agent` with `isolation: worktree`, `SendMessage`/`ListAgents`, background tasks, and `.claude/agents` frontmatter.
- Context band rationale: [[context-window-smart-zone]] in operator memory.

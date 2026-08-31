# Development Harness Plugin

Create a project-aware Claude Code development harness from either:

- a blank or planning-only project folder, or
- an existing repository that needs its first harness or an upgrade.

## Commands

```text
/development-harness:setup [new | existing | upgrade] [optional context]
/development-harness:audit [optional focus]
/development-harness:spec [task name or description]
/development-harness:session [launch | list | read | sweep] [task, id, or tier]
/development-harness:agent [the need] [optional tier]
```

`setup` and `audit` bootstrap and inspect a harness. The other three drive one that is
already installed, and they follow the loop the architecture describes: **decide, then
specify, then dispatch, then verify.**

- **`spec`** turns an accepted decision into a self-contained contract under
  `.ai/specs/`. A delegate does not get the conversation; it gets this file.
- **`session`** turns a capability tier into the exact launch command that enforces it,
  reads the `.ai/bus/` return channel, and sweeps background sessions the repository
  left running. It prints launch commands rather than running them.
- **`agent`** synthesizes a bounded agent for a need the harness did not foresee.
  Authority comes from the tier, never from the request.

`session` and `agent` require a Standard or Fleet harness. Lite has no generated agents
and therefore nothing to manage.

Greenfield setup interviews product intent, MVP scope, technical direction, agent roles, safety, and Git policy. It generates durable project context under `.ai/project/` and can optionally prepare—but never execute—the first scaffold contract.

Existing-project setup inspects safe repository evidence, discovers real commands and conventions, and installs through staging, validation, dry-run, and deliberate conflict handling.

The setup command never installs dependencies, initializes Git, scaffolds application code, calls a delegate, commits, pushes, or deploys.

## Permissions

`setup` and `audit` pre-approve only their own deterministic scripts, so a long
interview does not prompt a dozen times. `spec`, `session`, and `agent` pre-approve
nothing: they write files or dispatch agents, they are short, and the cheaper answer
there is the safer one. Every command is user-invocable only.

See the marketplace repository README for installation and full documentation.

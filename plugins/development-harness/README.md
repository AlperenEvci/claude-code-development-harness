# Development Harness Plugin

Create a project-aware Claude Code development harness from either:

- a blank or planning-only project folder, or
- an existing repository that needs its first harness or an upgrade.

## Commands

```text
/development-harness:setup [new | existing | upgrade] [optional context]
/development-harness:audit
```

Greenfield setup interviews product intent, MVP scope, technical direction, agent roles, safety, and Git policy. It generates durable project context under `.ai/project/` and can optionally prepare—but never execute—the first scaffold contract.

Existing-project setup inspects safe repository evidence, discovers real commands and conventions, and installs through staging, validation, dry-run, and deliberate conflict handling.

The setup command never installs dependencies, initializes Git, scaffolds application code, calls a delegate, commits, pushes, or deploys.

See the marketplace repository README for installation and full documentation.

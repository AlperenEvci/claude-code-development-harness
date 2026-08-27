# Development Harness Plugin

This directory is the Claude Code plugin root.

## Commands

```text
/development-harness:setup [optional project context]
/development-harness:audit [optional audit focus]
```

## Design

The setup skill is the interactive control plane. Python scripts perform deterministic inspection, rendering, validation, and post-install checks. Generated output is staged under `${CLAUDE_PLUGIN_DATA}` before any project file is touched.

The plugin intentionally ships no active hooks, MCP servers, or default settings.

## Project-specific output

In addition to the selected Lite/Standard/Fleet core, setup can render path-scoped rules, manual project workflow skills, and read-only domain researchers. Custom components are generated only for a concrete recurring need and cannot widen tool permissions.

#!/usr/bin/env bash
# A small repository with a partial harness, so the audit has real evidence to read
# without the fixture becoming a second thing to maintain.
set -eu

mkdir -p src .claude/skills/deploy .ai/reports

cat > AGENTS.md <<'MD'
# Project Engineering Contract

## Project

**Checkout Service**

Stage: `production`

## Stack

- Languages: Python
- Package manager: pip

## Commands

- **Test:** `python -m pytest`
- **Lint:** `python -m ruff check .`

## Do not

- Do not run destructive git commands on the user's behalf.
MD

cat > CLAUDE.md <<'MD'
@AGENTS.md

# Orchestration

Classify the task, gather only the context the decision needs, then act.
MD

cat > src/checkout.py <<'PY'
def total(items):
    return sum(item["price"] for item in items)
PY

cat > .claude/skills/deploy/SKILL.md <<'MD'
---
name: deploy
description: Ship the checkout service.
---

Run the deploy pipeline.
MD

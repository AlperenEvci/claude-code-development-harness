#!/usr/bin/env bash
# A repository that already carries a generated harness, holding a one-word defect.
# The harness is the full apparatus - artifacts, routing, roles - which is exactly the
# condition under which an agent is most tempted to use it on work that does not need
# any of it.
set -eu

mkdir -p src .ai/reports .ai/decisions .ai/specs .claude/agents

cat > AGENTS.md <<'MD'
# Project Engineering Contract

## Project

**Checkout Service**

Stage: `production`

## Stack

- Languages: JavaScript
- Package manager: npm

## Commands

- **Test:** `npm test`
- **Lint:** `npm run lint`

## Definition of done

For meaningful code changes: inspect the diff, run the smallest relevant check while
iterating, then run the full gate before declaring completion.

## Do not

- Do not run git commit or git push on the user's behalf.
MD

cat > CLAUDE.md <<'MD'
@AGENTS.md

# Claude Code Project Orchestration

## Working model

For non-trivial tasks:

1. Classify the task as trivial, standard, or complex.
2. Delegate noisy codebase exploration to a read-only researcher when useful.
3. Write a self-contained implementation spec before delegating precise implementation.
4. Independently inspect and verify the result.

Do not run the full pipeline for obvious one-line changes.

## Project knowledge

- `.ai/reports/`: codebase evidence and research
- `.ai/decisions/`: accepted durable decisions
- `.ai/specs/`: self-contained execution contracts
MD

cat > src/ui.js <<'JS'
export function renderCheckoutButton() {
  const button = document.createElement("button");
  button.className = "checkout-primary";
  button.textContent = "Sumbit";
  return button;
}
JS

cat > src/cart.js <<'JS'
export function subtotal(items) {
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}
JS

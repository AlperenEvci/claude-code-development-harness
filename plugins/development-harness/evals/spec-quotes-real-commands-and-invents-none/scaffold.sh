#!/usr/bin/env bash
# A harnessed JavaScript repository. The stack matters: every command in AGENTS.md is a
# node command, so any Python or Rust or Go verification step appearing in a generated
# contract was invented rather than read.
set -eu

mkdir -p src .ai/specs .ai/decisions .ai/reports

cat > AGENTS.md <<'MD'
# Project Engineering Contract

## Project

**Billing Service**

Stage: `production`

## Stack

- Languages: JavaScript
- Package manager: npm

## Commands

- **Test:** `npm test`
- **Lint:** `npm run lint`
- **Typecheck:** `npm run typecheck`
- **Full gate:** `npm run verify`

## Definition of done

For meaningful code changes: inspect the diff, run the smallest relevant check while
iterating, then run the full gate before declaring completion.

## Do not

- Do not run git commit or git push on the user's behalf.
MD

cat > CLAUDE.md <<'MD'
@AGENTS.md

# Claude Code Project Orchestration

Write a self-contained implementation spec before delegating precise implementation.

## Project knowledge

- `.ai/specs/`: self-contained execution contracts
- `.ai/decisions/`: accepted durable decisions
MD

cat > src/retry.js <<'JS'
export async function retryCharge(charge, attempts = 3) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const result = await submit(charge);
    if (result.ok) return result;
  }
  throw new Error("charge failed after retries");
}
JS

cat > .ai/decisions/0001-retry-idempotency.md <<'MD'
# Retries must be idempotent

Status: accepted

Duplicate charges have been observed when a retry lands after the original succeeded.
The retry path needs an idempotency key carried through to the processor.
MD

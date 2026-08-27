# Adaptive Interview

Use this as a question bank, not a form to dump on the user. Ask only unresolved questions and no more than five at a time.

## A. Project identity

1. Is this a new repository, an existing repository without a harness, or an existing harness to audit?
2. What does the product do, who uses it, and what is the current stage: experiment, MVP, production, regulated/critical?
3. Is the project a monorepo? Which folders are independently deployable or governed?

## B. Stack and repository reality

4. What languages, frameworks, runtimes, package managers, databases, and deployment targets are used?
5. Which directories are architectural boundaries?
6. Which files already act as sources of truth: README, architecture docs, ADRs, schemas, API specs?
7. Are there generated files or vendor directories agents must not edit?

Prefer inspecting package manifests and repository files over asking the user to remember exact versions.

## C. Verification

8. What exact commands install dependencies, run locally, lint, typecheck, test, and build?
9. Which command is the minimum fast gate? Which command is the full release gate?
10. Are tests reliable? Which important behaviors lack coverage?
11. Are there database, browser, mobile, infrastructure, or external-service tests requiring special setup?

Never invent commands. If unknown, mark them as discovery tasks.

## D. Team and Git workflow

12. Solo or team repository?
13. Branches, pull requests, trunk-based development, or direct commits?
14. May agents commit? May they push? May they open pull requests?
15. Are uncommitted human edits common?
16. For parallel writes, are worktrees acceptable?

Default: agents may edit locally but do not commit, push, or publish without explicit permission.

## E. Agent stack

17. Which tools are available: Claude Code, Codex CLI/App, ChatGPT Work, Cursor, others?
18. Which tool should be the main orchestrator?
19. Which models/tiers are available and economically abundant or scarce?
20. Should Codex use its configured default model, or is a specific model/reasoning level required?
21. Should the harness work when only one of Claude or Codex is available?

Route by role and difficulty; avoid model-name hardcoding when availability is uncertain.

## F. Autonomy and security

22. Preferred autonomy:
   - read-only planning,
   - edits with approval,
   - repository-scoped autonomous edits,
   - isolated autonomous lanes.
23. May agents access the network?
24. Are there secrets, customer data, health/financial/legal data, production credentials, or destructive infrastructure?
25. Which commands or directories are explicitly prohibited?
26. Should hooks be disabled or supplied only as reviewed examples? Version 0.1 never activates hooks.

Default: no network, no secrets, no bypass permissions, no active hooks, no destructive commands.

## G. Context and memory

27. What durable context must every agent know?
28. What information changes frequently and should not be persistent?
29. Are prior decisions or research reports available?
30. Who maintains the backlog and decision records?
31. Should `.ai/runs/` be committed, ignored, or periodically archived?

Default: reports/decisions/specs committed when useful; transient run logs ignored.

## H. Recurrent work and failure patterns

32. Which tasks repeat: feature development, review, migrations, design-system work, data imports, release?
33. What mistakes do agents repeat?
34. Where do context loss, architecture drift, or bad tests occur?
35. Which workflows deserve dedicated skills?
36. Which noisy investigations deserve subagents?
37. Which stable conventions apply only to particular paths and therefore belong in scoped rules?

Do not create a skill, agent, or scoped rule without a repeated, concrete purpose.

## I. Output and rollout

38. Desired tier: let the architect choose, or constrain it?
39. Should installation be one-shot, manual, or both?
40. Should existing files be merged, preserved, or replaced after backup?
41. Who else will use the harness?
42. Is a plugin/distribution package needed now, or only a personal skill?

## Minimum viable interview

For a straightforward project, the minimum set is:

1. Project purpose/stage.
2. Stack and repository type.
3. Exact verification commands.
4. Main agent tools.
5. Autonomy/security boundary.
6. Git/team workflow.
7. Existing agent files and recurring mistakes.

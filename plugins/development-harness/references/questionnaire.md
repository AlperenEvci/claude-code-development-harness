# Adaptive Interview

Use this as a question bank, not a form to dump on the user. Ask only unresolved questions and no more than five at a time.

## 0. Entry path

1. Is the target an empty/planning-only folder, an existing project without a harness, or an existing harness to upgrade?
2. Does the current folder actually belong to the intended project, or is Claude Code running one level too high/low?
3. For a Greenfield project, should setup be `context-only` or `ready-to-build`?

Use the inspector's `project_state` as evidence. An explicit operator statement is authoritative unless the directory scope is unsafe or clearly wrong.

## A. Greenfield product discovery

Ask these only for Create mode.

1. What is the project called?
2. What problem does it solve?
3. Who experiences that problem?
4. What concrete outcome should the product create?
5. What stage is this: idea, experiment, prototype, MVP, production-intent, regulated/critical?
6. What belongs in the first useful vertical slice?
7. What is explicitly out of scope for the MVP?
8. What are the core user or system workflows?
9. What milestones should come first?
10. Which product questions block implementation, and which can remain open?

Push back on oversized MVP scope. Prefer a small end-to-end slice to a broad list of disconnected features.

## B. Greenfield technical direction

Ask these only for Create mode and only after product intent is understood.

11. Is the target web, mobile, desktop, CLI, API, library, infrastructure, or multi-surface?
12. Does the operator have stack preferences, hard constraints, or permission to receive a recommendation?
13. What data must be stored, and what sensitivity/compliance concerns apply?
14. Is authentication required in the first slice?
15. Which external services or APIs are required?
16. What deployment target or operating environment is intended?
17. What source boundaries are planned?
18. Which install/dev/test/typecheck/lint/build commands are explicitly approved as the intended scaffold contract?
19. Is Git already initialized, should the user initialize it after setup, or should it be deferred?
20. Should setup generate a root README?

Recommendations are proposals, not repository evidence. Record assumptions and unresolved choices explicitly.

## C. Existing project identity and reality

Ask these for Adopt/Upgrade only when repository evidence is insufficient.

21. What does the product do, who uses it, and what is the current stage?
22. Is the project a monorepo? Which folders are independently deployable or governed?
23. What languages, frameworks, runtimes, package managers, databases, and deployment targets are used?
24. Which directories are architectural boundaries?
25. Which files already act as sources of truth: README, architecture docs, ADRs, schemas, API specs?
26. Are there generated files or vendor directories agents must not edit?

Prefer inspecting manifests and project files over asking the user to remember exact versions.

## D. Verification

27. What exact commands install dependencies, run locally, lint, typecheck, test, and build?
28. Which command is the minimum fast gate? Which command is the full release gate?
29. Are tests reliable? Which important behaviors lack coverage?
30. Are there database, browser, mobile, infrastructure, or external-service tests requiring special setup?

For Existing projects, commands should be repository evidence. For Greenfield, commands are approved plans until the scaffold creates and passes them. Never fabricate a gate.

## E. Team and Git workflow

31. Solo or team project?
32. Branches, pull requests, trunk-based development, or direct commits?
33. May agents commit? May they push? May they open pull requests?
34. Are uncommitted human edits common?
35. For established projects with parallel writes, are worktrees acceptable?

Default: agents may edit locally but do not commit, push, publish, or initialize Git without explicit permission.

## F. Agent stack

36. Which tools are available: Claude Code, OpenAI's official Codex Claude Code plugin, Codex CLI/App, Cursor, others?
37. Which tool should be the main orchestrator?
38. Which models/tiers are available and economically abundant or scarce?
39. Which implementation transport should be used: official Codex plugin, direct Codex CLI, or Claude-only?
40. Should the harness work when only one of Claude or Codex is available?

Route by role and difficulty; avoid model-name hardcoding when availability is uncertain.

## G. Autonomy and security

41. Preferred autonomy: read-only planning, edits with approval, repository-scoped autonomous edits, or isolated autonomous lanes?
42. May agents access the network?
43. Are there secrets, customer data, health/financial/legal data, production credentials, or destructive infrastructure?
44. Which commands or directories are explicitly prohibited?
45. Should hooks be disabled or supplied only as reviewed examples? Version 0.2 never activates hooks.

Default: no network, no secrets, no bypass permissions, no active hooks, no destructive commands.

## H. Context and memory

46. What durable context must every agent know?
47. What information changes frequently and should not be persistent?
48. Are prior decisions or research reports available?
49. Who maintains the backlog and decision records?
50. Should `.ai/runs/` be committed, ignored, or periodically archived?

For Greenfield, product intent lives under `.ai/project/`; after implementation exists, reports describe repository evidence.

## I. Recurrent work and failure patterns

51. Which tasks repeat: feature development, review, migrations, design-system work, data imports, release?
52. What mistakes do agents repeat?
53. Where do context loss, architecture drift, or bad tests occur?
54. Which workflows deserve dedicated skills?
55. Which noisy investigations deserve subagents?
56. Which stable conventions apply only to particular paths and therefore belong in scoped rules?

Do not create a skill, agent, or scoped rule without a repeated, concrete purpose.

## Minimum viable interviews

### Greenfield

1. Problem, users, and primary outcome.
2. MVP goals, non-goals, and core workflows.
3. Stack direction and material constraints.
4. Initial milestones and blocking questions.
5. Execution transport and autonomy/security boundary.
6. `context-only` or `ready-to-build`.

### Existing project

1. Project purpose/stage.
2. Exact verification commands.
3. Main agent tools and execution transport.
4. Autonomy/security boundary.
5. Git/team workflow.
6. Existing agent files and recurring mistakes.

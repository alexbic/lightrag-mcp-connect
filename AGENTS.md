# Agent Instructions

This public connector repository is operated by multiple AI agents. Minimize rediscovery: read the project state files before changing code.

## Required Reading Order
1. `PROJECT.md` — identity, goal, and layout.
2. `STATUS.md` — current state and next action.
3. `SPEC.md` — source of truth for behavior.
4. `PLAN.md` — current implementation phases.
5. `TECH_STACK.md` — tools, stack, commands, and deployment assumptions.
6. `BACKLOG.md` — task list.
7. `ROADMAP.md` — milestone context.

Read only what you need from long implementation files after this orientation.

## Operating Rules
- Current release track is **managed backend mode**.
- Do not implement external LightRAG proxy mode unless the user explicitly starts that phase.
- Keep public-facing names clear for first-time self-hosters.
- Use `LIGHTRAG_ADMIN_KEY` for the owner/admin key name.
- Keep `LIGHTRAG_SERVER_KEY` internal only.
- Never print secrets, raw deployment env, API keys, passwords, tokens, or signed URLs.
- For hosted deployment work, inspect the current configuration read-only first and avoid exposing environment values.
- When deploying a new commit, use the deployment platform's build/deploy action; do not assume a restart automatically uses the latest source.

## Keep Project Files Current
Any non-trivial change must update the project state files in the same work session.

- If behavior, scope, architecture, or acceptance criteria change, update `SPEC.md`.
- If implementation steps, sequencing, or phase ownership changes, update `PLAN.md`.
- If milestone status changes, update `ROADMAP.md`.
- If tasks are added, started, blocked, reviewed, or completed, update `BACKLOG.md`.
- If current deployment/local status, verification, blockers, or next actions change, update `STATUS.md`.
- If dependencies, tools, commands, env vars, Docker/deployment assumptions, or runtime versions change, update `TECH_STACK.md`.
- If repository purpose, layout, ownership, or operating model changes, update `PROJECT.md`.
- If agent workflow rules change, update this `AGENTS.md`.

Do not leave these files stale after implementing code, deployment changes, migrations, or substantial plans. If a change is intentionally code-only and none of the project files need updates, mention that in the final handoff.

## Verification
Before claiming a code change is done, run the relevant checks from `TECH_STACK.md`.

If Docker is unavailable, say so explicitly and leave Docker build verification as pending.

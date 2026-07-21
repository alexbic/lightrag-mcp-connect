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
- For this repository, do not commit `uv.lock` files created by local `uv` development or verification runs. Treat them as local tooling artifacts unless maintainers explicitly decide to version them later.
- Never print secrets, raw deployment env, API keys, passwords, tokens, or signed URLs.
- Because this is a public repository, do not write personal, customer-specific, internal-server, private-domain, private-IP, organization, or family/project-specific details into committed instruction files. Use generic examples such as `example workspace`, `hosted deployment`, and `self-hoster`.
- For hosted deployment work, inspect the current configuration read-only first and avoid exposing environment values.
- When deploying a new commit, use the deployment platform's build/deploy action; do not assume a restart automatically uses the latest source.

## New Repository Bootstrap
When starting work in another repository, check whether it has this project-state structure:

- `AGENTS.md`
- `PROJECT.md`
- `SPEC.md`
- `PLAN.md`
- `ROADMAP.md`
- `BACKLOG.md`
- `STATUS.md`
- `TECH_STACK.md`

If the structure is missing, review the repository first, create the files with repository-appropriate content, and then continue the implementation work using those files as the shared operating context.

## Task State Protocol
Before starting any non-trivial repository work, make the task recoverable:

1. Add or update a `BACKLOG.md` item with:
   - owner lane such as `@backend`, `@docs`, `@qa`, or `@devops`;
   - short task title;
   - clear Definition of Done.
2. Move the item to `In Progress` when implementation starts.
3. Update `STATUS.md` with:
   - what is being worked on;
   - current assumptions;
   - known blockers or risks;
   - next action if the session stops.

## Task Sizing and Decomposition
Before implementation, assess task size and decompose when needed:

- If the task can be completed and verified in one focused pass, keep it as one `BACKLOG.md` item.
- If the task has multiple components, uncertain dependencies, deployment risk, or could overflow the context window, split it into smaller independently testable items.
- Each decomposed item must have its own Definition of Done and verification path.
- Prefer a sequence where each completed item leaves the repository in a working, reviewable state.
- Keep the parent goal visible in `PLAN.md` or `STATUS.md` so the pieces still assemble into the intended outcome.
- Do not start broad implementation until the decomposition is written down.

## Skills and Tools Check
Before doing specialized work, check whether an applicable skill, tool, or repository script already exists.

- Use available skills/tools for tasks such as project review, GitHub work, deployment operations, data analysis, document generation, browser/UI checks, or release workflows when they fit the task.
- Prefer repository scripts and documented commands over ad-hoc one-off commands.
- If no suitable skill/tool exists, follow these project instructions and document the manual workflow in `STATUS.md` or `PLAN.md` when it matters.
- If the same manual workflow is likely to repeat across repositories, propose creating a reusable skill. Create or update such a skill only when the user explicitly asks for it.
- Do not use a skill/tool as a shortcut around privacy, secret-handling, or task-state rules in this file.

## Fix and Verification Loop
When implementation or verification fails, do not stop at the first failure unless the next step would require new authority or unsafe action.

1. Classify the failure:
   - code/config defect;
   - missing dependency/cache;
   - network/sandbox/tooling problem;
   - unclear requirement or external blocker.
2. If it is a code/config defect, make the smallest focused fix and rerun the relevant check.
3. If it is an environment/tooling problem, try a safe documented workaround, such as a local cache directory, repository script, or approved tool invocation.
4. Repeat `fix -> verify -> record result` until:
   - all relevant checks pass;
   - the same blocker remains after reasonable attempts;
   - continuing would require secrets, destructive action, production mutation, or user approval.
5. Record each meaningful loop result in `STATUS.md` or `BACKLOG.md`, including commands that passed, failed, or were skipped.

Never mark a task complete while required verification is still blocked unless the user explicitly waives that verification.

## Decision Gate
When a task is blocked by a product, release, security, architecture, or deployment-direction decision, do not treat it as an ordinary technical blocker and do not choose silently.

1. Stop before irreversible work such as merging, releasing, deleting code, changing production deployment, or publishing credentials/config.
2. Record the decision point in `STATUS.md` and move or add a `BACKLOG.md` item to `Review`.
3. Present the maintainers with 2-3 concrete options, including:
   - what each option changes;
   - risks and rollback implications;
   - which option you recommend and why.
4. If the maintainer gives a clear decision, record it in `STATUS.md` or `PLAN.md`, then continue the task from the last safe checkpoint.
5. If no decision is available, leave the repository clean, preserve all findings in project files, and hand off the exact next question.

Examples that require a Decision Gate:

- `main` changed release direction relative to the planned merge.
- A stable rollback line conflicts with a new feature release line.
- A fix requires changing authentication, secret handling, or public API behavior.
- A deployment change could affect existing users or data.

During work, keep the project files current whenever there is a meaningful intermediate result:

- tests/checks run or intentionally skipped;
- partial implementation completed;
- blocker discovered;
- architecture or scope changed;
- deployment/configuration state changed.

At the end of the work session:

- move finished items to `Done` or unfinished items to `Review`/`To Do` with a clear next action;
- update `STATUS.md` so another agent can resume without reading the whole chat;
- update `PLAN.md`, `SPEC.md`, `ROADMAP.md`, or `TECH_STACK.md` when the work changed them;
- mention in the handoff which checks passed, failed, or were not run.

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

After `uv`-based local verification or debugging, check for newly created `uv.lock` files in the repository root or nested Python project folders. In this repository they should stay ignored and out of Git unless the maintainers explicitly change that policy.

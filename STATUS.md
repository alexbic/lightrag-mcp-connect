# Status: LightRAG MCP Gateway

**Updated:** 2026-07-21T20:34:00Z

## Summary
Managed backend mode is the current release track. The public connector repository owns both `mcp/app` and `gateway/app`; deployments should consume released versions from this repository instead of copying connector source into separate deployment repositories.

## Progress
- M1 Managed Backend Baseline: █████████░ 90%
- M2 Managed MCP Release: ███████░░░ 70%
- M3 Public Repository Polish: █████░░░░░ 50%
- M4 External LightRAG Proxy Mode: ░░░░░░░░░░ 0%

## Done
- Added managed workspace gateway.
- Implemented admin registry model: admin keys use `workspace_slug=NULL`, `is_admin=true`.
- Implemented workspace key isolation: normal keys are bound to one workspace.
- Simplified project structure to `gateway/app` and `mcp/app`.
- Renamed user-facing admin env to `LIGHTRAG_ADMIN_KEY`.
- Added project instruction files.
- Added recoverable task-state protocol for agents.
- Added task decomposition rule for large or risky work.
- Added skills/tools check rule before specialized work.
- Added fix-and-verification loop rule for agents.
- Verified MCP checks: 29 passed, mypy clean, black clean.
- Verified gateway checks: 8 passed, 1 skipped, mypy clean, black clean.
- Verified `deploy/docker-compose.gateway.yml`, `deploy/docker-compose.yml`, `deploy/docker-compose.full-example.yml`, and `deploy/docker-compose.traefik.yml` config.
- Verified `gateway/Dockerfile` build.
- Verified remote tag `v1.3.0` exists.
- Refreshed README and Compose release pins from `v1.1.0` to `v1.3.0`.

## In Work
- Merge execution paused after pre-checking `origin/main` and hitting a documented stop condition.

## Blockers
- `origin/main` now points to `2b555bc` (`revert: restore stable v1.1.0 without workspace routing`), which changes release and deployment assumptions relative to the managed backend merge plan. Per `PLAN.md`, stop before merging until the release direction is explicitly reconciled.

## Next
- Decide whether `main` should remain on the reverted stable line at `2b555bc` or resume the managed backend release track.
- If managed backend remains the target, rerun `PLAN.md` "Next Safe Merge Step" from a clean worktree after updating the merge plan to account for the `main` revert.
- Do not merge `feature/workspace-gateway` into `main` until that release-direction decision is recorded.
- Keep `BACKLOG.md` and `STATUS.md` updated before and during future repository work so interrupted sessions can be resumed safely.
- Decompose future large tasks into independently testable backlog items before implementation.
- Check applicable skills/tools before manual specialized workflows; propose a reusable skill when a workflow repeats.
- Use the fix-and-verification loop before declaring future verification blockers.

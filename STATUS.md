# Status: LightRAG MCP Gateway

**Updated:** 2026-07-21T20:46:00Z

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
- Added Decision Gate rule for product/release/security/deployment-direction blockers.
- Verified MCP checks: 29 passed, mypy clean, black clean.
- Verified gateway checks: 8 passed, 1 skipped, mypy clean, black clean.
- Verified `deploy/docker-compose.gateway.yml`, `deploy/docker-compose.yml`, `deploy/docker-compose.full-example.yml`, and `deploy/docker-compose.traefik.yml` config.
- Verified `gateway/Dockerfile` build.
- Verified remote tag `v1.3.0` exists.
- Refreshed README and Compose release pins from `v1.1.0` to `v1.3.0`.

## In Work
- Decision Gate resolved: `main` resumes the managed gateway release track, and legacy users remain on the reverted line by pinning `v1.1.0`.
- Re-running `PLAN.md` "Next Safe Merge Step" with that release decision recorded.

## Blockers
- None currently, as long as `origin/main` has not changed again since the Decision Gate resolution.

## Next
- Continue `PLAN.md` "Next Safe Merge Step": re-check branch cleanliness and divergence, merge `feature/workspace-gateway` into `main`, run full verification, and push.
- Preserve legacy stability guidance by keeping `v1.1.0` as the documented pin for users who need the old simple-mode line.
- Keep `BACKLOG.md` and `STATUS.md` updated before and during future repository work so interrupted sessions can be resumed safely.
- Decompose future large tasks into independently testable backlog items before implementation.
- Check applicable skills/tools before manual specialized workflows; propose a reusable skill when a workflow repeats.
- Use the fix-and-verification loop before declaring future verification blockers.
- Use the Decision Gate when a blocker requires maintainer choice instead of technical troubleshooting.

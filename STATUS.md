# Status: LightRAG MCP Gateway

**Updated:** 2026-07-21T18:55:00Z

## Summary
Managed backend mode is the current release track. The public connector repository owns both `mcp/app` and `gateway/app`; deployments should consume released versions from this repository instead of copying connector source into separate deployment repositories.

## Progress
- M1 Managed Backend Baseline: █████████░ 90%
- M2 Managed MCP Release: ██░░░░░░░░ 20%
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
- Verified MCP checks: 29 passed, mypy clean, black clean.
- Verified gateway checks: 8 passed, 1 skipped, mypy clean, black clean.
- Verified `deploy/docker-compose.gateway.yml` config and `gateway/Dockerfile` build.

## In Work
- Managed backend release hardening.
- Public MCP gateway-mode release preparation.

## Blockers
- None known for managed backend code.

## Next
- Finish the public managed gateway-aware MCP release.
- Update docs so first-time self-hosters can choose simple mode or managed gateway mode without reading implementation details.
- Keep `BACKLOG.md` and `STATUS.md` updated before and during future repository work so interrupted sessions can be resumed safely.

# Status: LightRAG MCP Gateway

**Updated:** 2026-07-21T18:50:00Z by @codex

## Summary
Managed backend mode is the current release track. Managed backend mode is implemented on the feature branch. The public connector repo now owns both `mcp/app` and `gateway/app`; private deployment should pin this repo instead of carrying connector source.

## Progress
- M1 Managed Backend Baseline: █████████░ 90%
- M2 Managed MCP Release: ██░░░░░░░░ 20%
- M3 Public Repository Polish: ████░░░░░░ 40%
- M4 External LightRAG Proxy Mode: ░░░░░░░░░░ 0%

## Done
- Restored and protected production LightRAG/Dokploy secrets.
- Added managed workspace gateway.
- Known from private deploy verification:
  - admin key row has `workspace_slug=NULL`, `is_admin=true`.
  - Ossi key is non-admin and bound to `ossi`.
- Verified Ossi cannot request `main`.
- Simplified project structure to `gateway/app` and `mcp/app`.
- Renamed user-facing admin env to `LIGHTRAG_ADMIN_KEY`.
- Added project instruction files.
- Verified MCP checks: 29 passed, mypy clean, black clean.
- Verified gateway checks: 8 passed, 1 skipped, mypy clean, black clean.
- Verified `deploy/docker-compose.gateway.yml` config and `gateway/Dockerfile` build.
- Verified local Docker build for `gateway/Dockerfile`.

## In Work
- Managed backend release hardening.
- Public MCP gateway-mode release preparation.

## Blockers
- None known for managed backend code.
- None known for managed backend code.

## Next
- Inspect public `lightrag-mcp-connect` branch and finish `v1.3.x`.
- Prepare and release the public managed gateway-aware MCP version.

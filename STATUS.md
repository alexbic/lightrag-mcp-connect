# Status: LightRAG MCP Gateway

**Updated:** 2026-07-21T22:25:00Z

## Summary
Managed backend mode is the current release track. The public connector repository owns both `mcp/app` and `gateway/app`; deployments should consume released versions from this repository instead of copying connector source into separate deployment repositories.

## Progress
- M1 Managed Backend Baseline: █████████░ 90%
- M2 Managed MCP Release: ████████░░ 80%
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
- Verified new `mcp/Dockerfile` build.
- Verified remote tag `v1.3.0` exists.
- Refreshed README and Compose release pins from `v1.1.0` to `v1.3.0`.
- Decision Gate resolved: `main` resumes the managed gateway track, while legacy users keep the old simple-mode line by pinning `v1.1.1`.
- Merged `feature/workspace-gateway` into `main`.
- Re-verified merged `main`: MCP checks 29 passed, gateway checks 8 passed with 1 skipped, Compose config validation passed, and `gateway/Dockerfile` built successfully.
- Switched remote deployment examples from direct `LIGHTRAG_BASE_URL` wiring to managed `LIGHTRAG_GATEWAY_URL`, added `mcp/Dockerfile`, and refreshed English/Russian/Spanish deployment docs plus `.env.example`.
- Re-verified changed stacks: `docker compose config --quiet` passed for `deploy/docker-compose.yml`, `deploy/docker-compose.traefik.yml`, `deploy/docker-compose.full-example.yml`, `deploy/docker-compose.gateway.yml`, and `deploy/docker-compose.simple.yml`.
- Re-verified code after the deployment/doc switch: MCP checks 29 passed, mypy clean, black clean; gateway checks 8 passed with 1 skipped, mypy clean, black clean.
- Follow-up audit found and fixed compose runtime wiring gaps that `docker compose config` cannot catch: managed remote services now share `lightrag-mcp-net`, and `docker-compose.gateway.yml` passes LLM/embedding provider env to gateway-managed LightRAG child processes.
- Corrected stale legacy guidance in `SPEC.md` from `v1.1.0` to `v1.1.1`.
- Replaced the old project-specific `ossi` examples in public docs/tests with neutral `example` workspace naming.
- Re-ran verification after the follow-up fixes: MCP checks passed, gateway checks passed, all Compose examples validated, and both `mcp/Dockerfile` and `gateway/Dockerfile` built successfully.

## In Work
- Phase 2 follow-up after the safe merge: verify admin tools and normal workspace isolation through MCP on the managed track.

## Blockers
- None known.

## Next
- Verify admin tools and normal workspace isolation through MCP on the merged track.
- Commit the reviewed deployment/doc/test changes when ready.
- Preserve legacy stability guidance by keeping `v1.1.1` as the documented pin for users who need the old simple-mode line.
- Keep `BACKLOG.md` and `STATUS.md` updated before and during future repository work so interrupted sessions can be resumed safely.
- Decompose future large tasks into independently testable backlog items before implementation.
- Check applicable skills/tools before manual specialized workflows; propose a reusable skill when a workflow repeats.
- Use the fix-and-verification loop before declaring future verification blockers.
- Use the Decision Gate when a blocker requires maintainer choice instead of technical troubleshooting.

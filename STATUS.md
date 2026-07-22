# Status: LightRAG MCP Gateway

**Updated:** 2026-07-22T00:55:00Z

## Summary
Managed backend mode is the current release track. The public connector repository owns both `mcp/app` and `gateway/app`; deployments should consume released versions from this repository instead of copying connector source into separate deployment repositories.

## Progress
- M1 Managed Backend Baseline: █████████░ 90%
- M2 Managed MCP Release: ██████████ 100%
- M3 Public Repository Polish: ███████░░░ 70%
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
- Verified Phase 2 MCP admin visibility and workspace isolation coverage on the managed track:
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev pytest -q tests/test_gateway_integration.py tests/test_dispatcher_and_mutations.py tests/test_security_and_contracts.py` → 29 passed.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev pytest -q tests/test_admin_auth.py tests/test_registry.py tests/test_registry_postgres.py` → 8 passed, 1 skipped.
- Prepared the managed workspace/gateway `v2.0.0` release line:
  - Updated MCP package version, advertised server version, and gateway package version to `2.0.0`.
  - Updated managed README and Compose release pins from `v1.3.0` to `v2.0.0`.
  - Reworded README release narrative so the current managed line is `v2.0.0`, while future per-user hosted identity work stays explicitly future.
- Re-ran the full verification loop for `v2.0.0` prep:
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev pytest -q` → 29 passed.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev mypy mcp/app` → clean.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev black --check mcp/app tests` → clean.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev pytest -q` → 8 passed, 1 skipped.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev mypy app` → clean.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev black --check app tests` → clean.
  - `docker compose -f deploy/docker-compose.gateway.yml config --quiet` → passed.
  - `docker compose -f deploy/docker-compose.yml config --quiet` → passed.
  - `docker compose -f deploy/docker-compose.traefik.yml config --quiet` → passed.
  - `docker compose -f deploy/docker-compose.full-example.yml config --quiet` → passed.
  - `docker compose -f deploy/docker-compose.simple.yml config --quiet` → passed.
  - `docker build -f gateway/Dockerfile -t lightrag-mcp-gateway-layout-smoke .` → passed.
  - `docker build -f mcp/Dockerfile -t lightrag-mcp-smoke .` → passed.
- Verification environment notes:
  - Initial `uv run` attempts failed under sandbox due blocked DNS/PyPI access; reran with temporary elevated network access and all Python checks passed.
  - Initial Docker builds failed under sandbox due denied Docker socket access; reran with temporary elevated Docker daemon access and both smoke builds passed.
- Documented repository policy for local `uv` lockfiles:
  - `uv.lock` and nested files such as `gateway/uv.lock` are treated as local development artifacts for this repository.
  - They stay ignored and must not be committed unless maintainers explicitly change policy later.
  - `.gitignore`, `AGENTS.md`, and `TECH_STACK.md` now record this expectation.

## In Work
- Managed backend hardening/readability cleanup remains open; the Phase 2 MCP admin-visibility follow-up is now verified.
- Some MCP clients appear to ignore `initialize.instructions` even though the
  server returns them. The MCP now exposes `get_agent_instructions` as a
  client-agnostic fallback, but this still needs downstream release/tag
  publication and live-client validation outside the repository.
- The next handshake-instructions cleanup is to stop serving one shared text to
  every caller. We need profile-specific instructions for connection mode and
  role: `stdio-user`, `stdio-admin`, `remote-user`, and `remote-admin`.
- Release strategy decision on 2026-07-22:
  - do not cut a new version just for the instruction-profile work yet;
  - keep polishing the current `v2.0.0` release line until the handshake
    instruction behavior is correct in real deployments;
  - after that, update the existing release line/deployment target rather than
    introducing another version bump during the active validation phase.

## Recently Done
- Closed the current `v2.0.0` release-polish pass for instruction profiles:
  - packaged wheel now includes all four profile-specific markdown files under
    `lightrag_mcp_connect/instructions/`;
  - README now includes a short first-time managed setup path plus immediate
    post-deploy steps;
  - README now documents that legacy `LIGHTRAG_MCP_INSTRUCTIONS_FILE` still
    works as a shared fallback.
- Tightened instruction-profile verification:
  - added tests for profile-specific env override precedence and legacy
    single-file fallback;
  - added test isolation for the active profile state between cases.
- Re-ran focused packaging/test verification after the release-polish pass:
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev pytest -q tests/test_dispatcher_and_mutations.py` → 18 passed.
  - `python3 -m pip wheel --no-build-isolation --no-deps . -w /tmp/lightrag-mcp-build` → passed.
  - inspected `/tmp/lightrag-mcp-build/lightrag_mcp_connect-2.0.0-py3-none-any.whl` and confirmed it contains:
    - `lightrag_mcp_connect/instructions/stdio-user__mcp-instructions.md`
    - `lightrag_mcp_connect/instructions/stdio-admin__mcp-instructions.md`
    - `lightrag_mcp_connect/instructions/remote-user__mcp-instructions.md`
    - `lightrag_mcp_connect/instructions/remote-admin__mcp-instructions.md`
- Added `mcp/app/instructions.py` so handshake-instruction loading is shared
  between server initialization and tool handlers.
- Added the `get_agent_instructions` MCP tool so clients that ignore
  `initialize.instructions` can fetch the active instruction text explicitly.
- Updated README agent-instructions docs to explain the fallback behavior.
- Added profile-specific handshake instruction selection:
  - supported profiles are `stdio-user`, `stdio-admin`, `remote-user`, and
    `remote-admin`;
  - profile-specific file names now use explicit prefixes such as
    `remote-admin__mcp-instructions.md`;
  - profile resolution supports `LIGHTRAG_MCP_CONNECTION_MODE`,
    `LIGHTRAG_MCP_INSTRUCTIONS_PROFILE`, `LIGHTRAG_MCP_INSTRUCTIONS_DIR`, and
    per-profile file override env vars;
  - `get_agent_instructions` now returns the active profile and the resolved
    source path, not just the raw instruction text.
- Re-ran focused MCP verification after the fallback change:
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev pytest -q tests/test_dispatcher_and_mutations.py` → 12 passed.
  - `MYPY_CACHE_DIR=/tmp/lightrag-mypy-cache UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev mypy mcp/app` → clean.
  - `UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev black --check mcp/app tests` → passed.

## Blockers
- None known.

## Next
- Finish the instruction-profile cleanup and live validation on the existing
  `v2.0.0` line before deciding whether any new version is needed.
- Test the updated `v2.0.0` line from another LightRAG project before drafting
  final release notes.
- Publish release notes that call out managed workspace/gateway mode as the
  stable line and preserve `v1.1.1` as the legacy rollback pin after
  downstream validation succeeds.
- Preserve legacy stability guidance by keeping `v1.1.1` as the documented pin for users who need the old simple-mode line.
- Keep `BACKLOG.md` and `STATUS.md` updated before and during future repository work so interrupted sessions can be resumed safely.
- Decompose future large tasks into independently testable backlog items before implementation.
- Check applicable skills/tools before manual specialized workflows; propose a reusable skill when a workflow repeats.
- Use the fix-and-verification loop before declaring future verification blockers.
- Use the Decision Gate when a blocker requires maintainer choice instead of technical troubleshooting.

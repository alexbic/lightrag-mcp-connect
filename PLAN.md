# Plan: LightRAG MCP Gateway

> Current implementation plan. Keep this short and update it when direction changes.

## Phase 1: Stabilize Managed Backend Mode
**Goal:** Make current managed gateway implementation readable, tested, and safe to release.

**DoD:**
- [x] Admin bootstrap migration works.
- [x] Rename user-facing admin env to `LIGHTRAG_ADMIN_KEY`.
- [x] Simplify repo structure to `gateway/app` and `mcp/app`.
- [x] Add project instruction files.
- [x] Confirm local Docker build after Docker is available.

## Phase 2: Switch MCP to Gateway Mode
**Goal:** Move MCP from fixed legacy simple mode to managed gateway-aware mode.

**DoD:**
- [ ] Resolve pending public `lightrag-mcp-connect` branch changes.
- [ ] Release/tag managed gateway-aware MCP version.
- [ ] Update example Compose from `v1.1.0` to that release.
- [ ] Use `LIGHTRAG_GATEWAY_URL` for MCP instead of `LIGHTRAG_BASE_URL`.
- [ ] Verify admin tools and normal workspace isolation through MCP.

## Phase 3: Harden Admin Key Model
**Goal:** Reduce confusion and blast radius around owner/admin keys.

**DoD:**
- [ ] Decide whether hosted deployments should use a `LIGHTRAG_ADMIN_KEY` distinct from legacy `LIGHTRAG_API_KEY`.
- [ ] Document recovery procedure if admin key is lost.
- [ ] Add tests for admin-only endpoint behavior.

## Phase 4: External LightRAG Mode
**Goal:** Add and test proxy mode for users who already run a compatible LightRAG server.

**DoD:**
- [ ] Define `WORKSPACE_BACKEND_MODE=external`.
- [ ] Forward validated workspace as `LIGHTRAG-WORKSPACE`.
- [ ] Add a separate external-mode test stack that treats a LightRAG server as externally managed.
- [ ] Document version/config requirements for external LightRAG.

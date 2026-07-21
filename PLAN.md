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
- [x] Resolve pending public `lightrag-mcp-connect` branch changes.
- [x] Release/tag managed gateway-aware MCP version.
- [x] Update example Compose from `v1.1.0` to that release.
- [ ] Merge `feature/workspace-gateway` into `main`.
- [ ] Use `LIGHTRAG_GATEWAY_URL` for MCP instead of `LIGHTRAG_BASE_URL`.
- [ ] Verify admin tools and normal workspace isolation through MCP.

### Next Safe Merge Step
**Goal:** Land the verified `feature/workspace-gateway` branch into `main` without losing release/history context.

**Decision Gate resolution (2026-07-21):**
- `main` resumes the managed gateway track.
- The reverted stable line remains available to legacy users by pinning `v1.1.0`.
- Continue the merge sequence, but still stop if `origin/main` changes again in a way that affects release or deployment assumptions.

**Pre-checks:**
- Confirm current branch is `feature/workspace-gateway`.
- Confirm `git status -sb` is clean.
- Confirm `origin/feature/workspace-gateway` contains local HEAD.
- Fetch `origin/main` and inspect divergence before merging.

**Merge sequence:**
1. Switch to `main`.
2. Fast-forward or merge `origin/main` if needed.
3. Merge `feature/workspace-gateway`.
4. Resolve conflicts only if they are obvious and local to project docs/layout changes; otherwise stop and record blocker.
5. Run relevant verification from `TECH_STACK.md`.
6. Push `main`.
7. Update `BACKLOG.md`, `STATUS.md`, and this `PLAN.md`.

**Stop conditions:**
- Dirty worktree before merge.
- Unexpected conflict in source, packaging, or deployment files.
- Required verification cannot pass after the fix-and-verification loop.
- Remote `main` has new commits that change release or deployment assumptions.

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

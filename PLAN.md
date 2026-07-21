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
- [x] Merge `feature/workspace-gateway` into `main`.
- [x] Use `LIGHTRAG_GATEWAY_URL` for MCP instead of `LIGHTRAG_BASE_URL`.
- [x] Verify admin tools and normal workspace isolation through MCP.
- [x] Prepare managed workspace/gateway `v2.0.0` release cut with aligned package versions, docs, Compose pins, and verification records.

### Next Safe Merge Step
**Goal:** Land the verified `feature/workspace-gateway` branch into `main` without losing release/history context.

**Completed on 2026-07-21:**
- `main` resumes the managed gateway track.
- The reverted stable line remains available to legacy users by pinning `v1.1.1`.
- `feature/workspace-gateway` merged cleanly into `main`.
- Relevant verification passed on merged `main`.

### Release Prep: v2.0.0
**Goal:** Publish the managed workspace/gateway line as the next stable public release while keeping `v1.1.1` as the explicit legacy rollback line.

**DoD:**
- [x] MCP package version, advertised server version, and gateway package version all report `2.0.0`.
- [x] Managed deployment docs and Compose defaults pin `v2.0.0`.
- [x] README wording no longer treats managed gateway mode as a `v1.x` feature or reserves `v2` for future hosted identity work.
- [x] Full verification loop from `TECH_STACK.md` is run again and recorded.
- [x] Release/tag plan is written down with legacy rollback guidance.

**Release/tag plan:**
1. Confirm the worktree contains only the reviewed `v2.0.0` prep changes and exclude any accidental local lockfiles or unrelated edits.
2. Commit the release-prep changes on `main` with a release-oriented message.
3. Create the managed release tag as annotated `v2.0.0` on that commit.
4. Publish release notes that call out managed workspace/gateway mode as the stable line and keep `v1.1.1` documented as the legacy simple-mode rollback pin.
5. After the tag exists remotely, keep the Compose examples and local `uvx` snippets pinned to `v2.0.0` as already prepared here.

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

# Spec: LightRAG MCP Gateway

> Source of truth for intended behavior. Update this before changing architecture.

## Goal
Run one LightRAG endpoint that supports many isolated workspaces without adding containers, ports, domains, or deployment environment variables per workspace.

## Users and Scenarios
- Owner/admin creates workspaces and issues keys.
- Workspace user receives a workspace key and can access only that workspace.
- Existing legacy `main` data remains available after migration.
- MCP clients can use the same endpoint while the gateway resolves workspace access.

## Functional Requirements
- F1: `gateway` validates client `X-API-Key` against PostgreSQL registry rows.
- F2: Admin keys have `workspace_slug=NULL` and `is_admin=true`.
- F3: Workspace keys have one `workspace_slug` and `is_admin=false`.
- F4: Normal workspace keys cannot override their assigned workspace with `LIGHTRAG-WORKSPACE`.
- F5: Admin keys may select a registered enabled workspace with `LIGHTRAG-WORKSPACE`; default is `main`.
- F6: `main` preserves LightRAG legacy empty workspace storage, mapping to existing PostgreSQL `default` rows.
- F7: `LIGHTRAG_ADMIN_KEY` is imported idempotently into the registry on startup as admin.
- F8: `LIGHTRAG_SERVER_KEY` is used only internally from gateway to child LightRAG servers.
- F9: Workspace creation/key issuance is a data operation, not an infrastructure operation.
- F10: Current release supports managed backend mode only.

## Non-Functional Requirements
- NF1: No secrets are committed or printed in logs/docs.
- NF2: Keys are stored only as HMAC-SHA256 hashes using `WORKSPACE_KEY_PEPPER`.
- NF3: Unknown, disabled, or mismatched workspaces fail closed.
- NF4: Local tests, type checks, format checks, and Compose config validation must pass before deploy.
- NF5: Hosted deployment changes require read-only inspection first and explicit deploy intent.

## Out of Scope for Current Release
- External LightRAG proxy mode.
- Per-client OAuth workspace mapping through the shared remote `/mcp` endpoint.
- Admin UI.
- Automatic key rotation policy.

## Acceptance Criteria
- [x] Managed gateway starts and preserves legacy `main`.
- [x] Example workspace exists and is isolated.
- [x] `LIGHTRAG_ADMIN_KEY` naming replaces bootstrap/admin legacy names in repo config.
- [x] Project structure uses `gateway/app` and `mcp/app`.
- [x] MCP is switched from legacy simple mode (`v1.1.1` pin) to managed gateway mode.
- [x] Public connector release/tag is finalized as managed workspace/gateway `v2.0.0`.

## Open Questions
- Should hosted deployments use a dedicated `LIGHTRAG_ADMIN_KEY` distinct from legacy `LIGHTRAG_API_KEY` before MCP gateway-mode rollout?
- The public managed backend track resumes on `main`; legacy users who need the old simple-mode behavior should pin `v1.1.1`.

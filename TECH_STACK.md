# Tech Stack

## Runtime
- Python 3.11+ for `gateway`.
- Python 3.10+ for `mcp`.
- Official upstream LightRAG image pinned by digest in `gateway/Dockerfile`.
- `lightrag-server` runs as child processes managed by the gateway in managed backend mode.

## Gateway
- FastAPI
- Uvicorn
- asyncpg
- httpx
- PostgreSQL registry tables:
  - `lightrag_workspaces`
  - `lightrag_workspace_keys`

## MCP
- Model Context Protocol Python SDK
- httpx
- pydantic
- anyio
- supergateway for stdio-to-streamable-HTTP wrapping in remote deployments
- Optional auth proxy in front of remote MCP deployments

## Storage
- PostgreSQL + pgvector for LightRAG KV/vector/doc status storage.
- Graph storage follows the user's LightRAG configuration.
- Docker volumes are defined by the selected Compose example.

## Key Environment Variables
- `LIGHTRAG_ADMIN_KEY`: owner/admin key imported into registry as `is_admin=true`.
- `LIGHTRAG_API_KEY`: client key used by MCP simple mode or by an MCP instance connecting to the gateway.
- `LIGHTRAG_MCP_CONNECTION_MODE`: selects instruction transport profile resolution, `stdio` or `remote`.
- `LIGHTRAG_MCP_INSTRUCTIONS_PROFILE`: optional explicit instruction profile override, one of `stdio-user`, `stdio-admin`, `remote-user`, `remote-admin`.
- `LIGHTRAG_MCP_INSTRUCTIONS_DIR`: optional directory containing profile-specific handshake instruction files named with prefixed filenames such as `remote-admin__mcp-instructions.md`.
- `LIGHTRAG_MCP_INSTRUCTIONS_<PROFILE>_FILE`: optional per-profile file override, for example `LIGHTRAG_MCP_INSTRUCTIONS_REMOTE_ADMIN_FILE`.
- `LIGHTRAG_SERVER_KEY`: internal gateway-to-child LightRAG key; never give to clients.
- `WORKSPACE_KEY_PEPPER`: HMAC pepper for workspace key hashing.
- `POSTGRES_*`: database connection.
- `LIGHTRAG_*_STORAGE`: LightRAG storage backends.
- `LLM_*`, `EMBEDDING_*`, `RERANK_*`: model provider configuration.

## Local Commands
```bash
UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev pytest -q
UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev mypy mcp/app
UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --extra dev black --check mcp/app tests

UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev pytest -q
UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev mypy app
UV_CACHE_DIR=/tmp/lightrag-mcp-cache uv run --directory gateway --extra dev black --check app tests

docker compose -f deploy/docker-compose.gateway.yml config --quiet
docker compose -f deploy/docker-compose.yml config --quiet
docker compose -f deploy/docker-compose.traefik.yml config --quiet
docker compose -f deploy/docker-compose.full-example.yml config --quiet
docker compose -f deploy/docker-compose.simple.yml config --quiet
docker build -f gateway/Dockerfile -t lightrag-mcp-gateway-layout-smoke .
docker build -f mcp/Dockerfile -t lightrag-mcp-smoke .
```

## Local `uv` Artifact Policy
- In this repository, `uv.lock` is treated as a local development artifact when created by `uv run` during verification, debugging, or ad-hoc local work.
- Do not commit repository-root `uv.lock` or nested project lockfiles such as `gateway/uv.lock` unless maintainers explicitly decide to start versioning them.
- Keep these files ignored in Git and clean them up after local `uv` workflows if they appear.
- This policy is specific to this repository style: a public connector/library workflow where production builds currently use `pip install .` and runtime/deploy paths do not require checked-in `uv.lock` files.

## Deployment Notes
- Use released tags for production deployments.
- Remote managed deployments now route MCP through `LIGHTRAG_GATEWAY_URL` to the bundled `lightrag-gateway`; direct `LIGHTRAG_BASE_URL` wiring is kept for simple mode only.
- Do not commit `.env` files or real secrets.
- Keep the gateway internal server key private.
- If using a hosting platform, inspect current deployed config before changing it.

## Notes for Agents
- Prefer `rg` for search.
- Do not print secrets.
- Do not use destructive git commands unless the user explicitly asks for them.
- Keep project state files current when behavior, plans, or verification status changes.

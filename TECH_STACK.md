# Tech Stack

## Runtime
- Python 3.11+ for `gateway`.
- Python 3.10+ for `mcp`.
- Official upstream LightRAG image pinned by digest in `gateway/Dockerfile`.
- `lightrag-server` runs as child processes managed by the gateway.

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
- supergateway for stdio-to-streamable-HTTP wrapping in production Compose
- mcp-auth-proxy for remote OAuth front door in production

## Storage
- PostgreSQL + pgvector for LightRAG KV/vector/doc status storage.
- NetworkX graph storage for current production graph mode.
- Docker volumes:
  - `lightrag-data`
  - `lightrag-inputs`
  - `lightrag-db-data`
  - auth proxy data volume

## Key Environment Variables
- `LIGHTRAG_ADMIN_KEY`: owner/admin key imported into registry as `is_admin=true`.
- `LIGHTRAG_API_KEY`: legacy/client key, still used by MCP simple mode and homelab migration alias.
- `LIGHTRAG_SERVER_KEY`: internal gateway-to-child LightRAG key; never give to clients.
- `WORKSPACE_KEY_PEPPER`: HMAC pepper for workspace key hashing.
- `POSTGRES_*`: database connection.
- `LIGHTRAG_*_STORAGE`: LightRAG storage backends.
- `LLM_*`, `EMBEDDING_*`, `RERANK_*`: model provider configuration.

## Local Commands
```bash
UV_CACHE_DIR=/tmp/lightrag-uv-cache-refactor uv run --directory gateway --extra dev pytest -q
UV_CACHE_DIR=/tmp/lightrag-uv-cache-refactor uv run --directory gateway --extra dev mypy app
UV_CACHE_DIR=/tmp/lightrag-uv-cache-refactor uv run --directory gateway --extra dev black --check app tests

UV_CACHE_DIR=/tmp/lightrag-uv-cache-refactor uv run --directory mcp --extra dev pytest -q
UV_CACHE_DIR=/tmp/lightrag-uv-cache-refactor uv run --directory mcp --extra dev mypy app
UV_CACHE_DIR=/tmp/lightrag-uv-cache-refactor uv run --directory mcp --extra dev black --check app tests

docker compose -f deploy/docker-compose.lightrag-homelab.yml config --quiet
docker compose -f deploy/docker-compose.lightrag.yml config --quiet
docker build -f gateway/Dockerfile -t lightrag-gateway-layout-smoke .
```

## Production Tools
- Dokploy for deployment.
- Organization: `alexbic.net`.
- Private deploy compose: `lightrag-homelab`.
- Server SSH: `ssh homelab-ugreen-vm`.
- Use Dokploy API with `X-API-Key`; never print environment values.
- For a new commit, use Dokploy `compose.deploy`, not `compose.redeploy`.

## Notes for Agents
- Prefer `rg` for search.
- Do not print secrets.
- Do not use destructive git commands.
- Before Dokploy changes, read `AGENTS.md` and use the Dokploy skill workflow.


# LightRAG Workspace Gateway

One public LightRAG-compatible endpoint with dynamically registered workspaces.
Each workspace is backed by an official `lightrag-server` process created lazily
inside the gateway container. Adding a workspace never changes Compose, ports,
domains, or Dokploy environment.

```bash
docker exec lightrag lightrag-workspace create ossi --display-name "Ossi"
```

The command returns the workspace API key once. Give that key to the client as
its normal `LIGHTRAG_API_KEY`. The gateway stores only an HMAC-SHA256 digest and
automatically routes every request made with that key to `workspace=ossi`.

The logical `main` workspace deliberately launches LightRAG with its historical
empty workspace value, so existing PostgreSQL `default` rows and root-level
NetworkX data remain visible after migration.

Required secrets:

- `LIGHTRAG_SERVER_KEY`: internal key used only between the gateway and child servers.
- `WORKSPACE_ADMIN_KEY`: protects create/list/rotate/revoke operations.
- `WORKSPACE_KEY_PEPPER`: random value of at least 32 characters used to hash client keys.

PostgreSQL connection uses the existing `POSTGRES_*` variables. The registry
tables are created idempotently at startup.

The Dockerfile pins the tested upstream LightRAG image digest. Upgrade that
digest deliberately after running the unit, PostgreSQL, and gateway E2E tests.

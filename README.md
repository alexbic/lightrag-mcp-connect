# lightrag-mcp-connect

**English** | [Русский](README.ru.md) | [Español](README.es.md)

MCP server for connecting Claude and other MCP clients to a
[LightRAG](https://github.com/HKUDS/LightRAG) knowledge base.

This fork adds reliable document upload from local files, URLs, and text. It
also provides explicit commands for replacing and appending to documents.

## Requirements

- A running LightRAG server
- A LightRAG API key
- [`uv`](https://docs.astral.sh/uv/) for local use

## Local setup

Add this server to your MCP client configuration:

```json
{
  "mcpServers": {
    "lightrag": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alexbic/lightrag-mcp-connect.git@v1.1.0",
        "lightrag-mcp-connect"
      ],
      "env": {
        "LIGHTRAG_BASE_URL": "http://localhost:9621",
        "LIGHTRAG_API_KEY": "your-api-key",
        "LIGHTRAG_FILE_PATH_ROOT": "/Users/you/Documents"
      }
    }
  }
}
```

`LIGHTRAG_FILE_PATH_ROOT` is optional. Set it only when the MCP server must read
local files. Files outside this directory are rejected.

Restart the MCP client after changing its configuration.

## Document commands

### Create a document

Use one source:

```text
upload_document(file_path)
upload_document(file_url)
upload_document(filename, text_content)
```

### Replace a document

The document with the same filename is deleted and indexed again with the new
content:

```text
update_document(file_path)
update_document(file_url)
update_document(filename, text_content)
```

### Append text

```text
append_text(filename, text_content)
```

`append_text` is available for text documents managed by this MCP server. For
an existing external document, run `update_document` once with its complete
text before appending.

LightRAG rebuilds the knowledge graph automatically after document changes.
Graph commands are only needed for direct entity or relation management.

## Other commands

The server also provides:

- document listing, status, scanning, and deletion
- knowledge-base queries
- graph inspection and entity/relation management
- LightRAG health and pipeline status

The obsolete `insert_text` and `insert_texts` commands are not exposed.

## Remote setup

The `deploy/` directory contains ready configurations for remote MCP access
through HTTPS and OAuth.

```bash
git clone https://github.com/alexbic/lightrag-mcp-connect.git
cd lightrag-mcp-connect/deploy
cp .env.example .env
```

Set `DOMAIN`, `LIGHTRAG_URL`, `LIGHTRAG_API_KEY`, and `MCP_AUTH_PASSWORD` in
`.env`, then start one configuration:

```bash
# Caddy
docker compose -f docker-compose.yml up -d --build

# Existing Traefik
docker compose -f docker-compose.traefik.yml up -d --build
```

To run LightRAG and the MCP gateway together, use
`docker-compose.full-example.yml`.

Add the remote connector URL to your MCP client:

```text
https://mcp.example.com/mcp
```

## Configuration

| Variable | Purpose |
|---|---|
| `LIGHTRAG_BASE_URL` | LightRAG server URL |
| `LIGHTRAG_API_KEY` | LightRAG API key |
| `LIGHTRAG_FILE_PATH_ROOT` | Allowed directory for `file_path` |
| `LIGHTRAG_MCP_CONTENT_DB` | Optional SQLite path used by `append_text` |
| `LIGHTRAG_TIMEOUT` | Request timeout in seconds |

URL downloads reject private network addresses and are limited to 50 MB.

## Origin

Forked from
[desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp).
The fork was created to support remote document uploads and a tested remote MCP
deployment while keeping local stdio usage simple.

## License

MIT. See [LICENSE](LICENSE).

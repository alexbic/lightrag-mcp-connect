# lightrag-mcp-remote

**English** | [Русский](README.ru.md) | [Español](README.es.md)

Remote, OAuth-protected MCP access to a [LightRAG](https://github.com/HKUDS/LightRAG)
knowledge base — connect from claude.ai (web/mobile), Claude Desktop, or
Claude Code from anywhere, not just a machine that happens to run LightRAG
locally.

This is a fork of [desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp)
(MIT licensed, kept in `LICENSE`), plus a complete `deploy/` recipe for
running it as a remote MCP server: [supergateway](https://github.com/supercorp-ai/supergateway)
(stdio → streamable-HTTP) fronted by [mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy)
(OAuth 2.1). Every piece of this was built and verified against a real
production LightRAG deployment — the compose files under `deploy/` are
what's actually running, not an untested sketch.

## Why this exists

LightRAG's own MCP story is thin — no native MCP endpoint, and the
community wrapper (`daniel-lightrag-mcp`) only works when the MCP client
and the MCP server share a filesystem (i.e. local stdio, one machine).
That's fine for Claude Desktop on your own laptop talking to a local
LightRAG. It falls apart the moment you want claude.ai on your phone to
reach the same knowledge base — there's no shared filesystem between
Anthropic's infrastructure and your server, and the tool's `upload_document`
literally fails with `File does not exist` no matter what path you give it,
because it's trying to open that path *locally on the MCP server*, not on
the caller's machine.

Getting this working end to end also meant fixing (and documenting, below)
several non-obvious problems along the way:

- `supercorp/supergateway:uvx` has no `git` binary, so `uvx --from git+URL`
  fails at container start — see `deploy/mcp-gw/Dockerfile`.
- supergateway's `--stateful` mode requires clients to resend a session
  header on every request; Claude's client doesn't reliably do that, so
  every connection died right after `initialize` with a cryptic "no tools
  available" in the Claude UI. Fixed by *not* using `--stateful`.
- supergateway's bundled MCP SDK only recognizes protocol versions up to
  `2025-06-18` and hard-rejects the `MCP-Protocol-Version: 2025-11-25`
  header Claude sends on every request after `initialize` — same "no
  tools available" symptom, different cause. Fixed with a reverse-proxy
  header rewrite (Caddy or Traefik, see `deploy/`).
- `upload_document` only accepted a server-side `file_path` — see below,
  this is the actual code fix in this fork.

None of this is LightRAG's fault, and none of it is really
`daniel-lightrag-mcp`'s fault either — it's what happens when you take a
local-stdio-shaped tool and stretch it across a network boundary. This
repo is the result of doing that stretching once, properly, so you don't
have to.

## What's fixed here vs. upstream

`upload_document` in upstream `daniel-lightrag-mcp` only accepts
`file_path`, which it reads **locally on the MCP server process** — not
on the machine of whoever is calling the tool. Over stdio on your own
laptop those are the same machine, so it's invisible. Over a remote MCP
connection (Claude web/mobile/Desktop → this gateway, running on a
server), they're never the same machine, and the tool just fails.

This fork adds `file_content` (base64) + `filename` as an alternative:
the content travels inside the tool call itself, no shared filesystem
needed. `file_path` is kept for same-machine / local-stdio setups where
it still makes sense.

```jsonc
// Before (only works if the MCP server can read this path itself):
{ "file_path": "/some/local/path.pdf" }

// After (works regardless of where the calling agent runs):
{ "file_content": "<base64 bytes>", "filename": "report.pdf" }
```

## Architecture

```
claude.ai / Claude Desktop / Claude Code / mobile app
  │  https://mcp.example.com/mcp  (OAuth 2.1 Bearer token)
  ▼
Caddy or Traefik  ──  TLS + rewrites MCP-Protocol-Version header
  ▼
lightrag-mcp-auth (mcp-auth-proxy)  ──  OAuth 2.1: DCR, PKCE, discovery,
  │                                     one-time password login
  ▼  (private network only, no auth needed — not internet-reachable)
lightrag-mcp-gw (supergateway)  ──  stdio ⇄ streamable-HTTP, stateless
  ▼
lightrag-mcp-remote (this repo, via uvx-from-git)  ──  the actual MCP tool
  ▼  X-API-Key
your LightRAG instance
```

`lightrag-mcp-gw` is never exposed directly — only `lightrag-mcp-auth`
faces the internet, and it forwards to the gateway over a private docker
network.

## Deploying

You need an existing LightRAG instance already running somewhere
reachable from this stack. Don't have one? See
[HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — this repo only adds
the remote-MCP layer on top.

```bash
git clone https://github.com/alexbic/lightrag-mcp-remote.git
cd lightrag-mcp-remote/deploy
cp .env.example .env
# edit .env: DOMAIN, LIGHTRAG_URL, LIGHTRAG_API_KEY, MCP_AUTH_PASSWORD

# No existing reverse proxy — Caddy handles TLS automatically:
docker compose -f docker-compose.yml up -d --build

# Already running Traefik? Also set TRAEFIK_NETWORK in .env, then:
docker compose -f docker-compose.traefik.yml up -d --build
```

Using a different reverse proxy entirely? See the comment block at the
top of `docker-compose.traefik.yml` — two requirements, with nginx and
Caddy examples.

## Connecting Claude

In claude.ai (or Claude Desktop, or Claude Code): **Settings → Connectors
→ Add custom connector**, enter:

```
https://mcp.example.com/mcp
```

Leave Client ID / Client Secret blank — `mcp-auth-proxy` handles OAuth
Dynamic Client Registration itself. You'll be redirected to a one-time
login screen (the `MCP_AUTH_PASSWORD` you set); after that, Claude
manages its own OAuth token refresh and you won't need the password
again until you re-authorize a new client.

## Tools

20 tools are exposed via `tools/list` — document management (insert,
upload, scan, retrieve, delete), querying (regular + streaming), knowledge
graph (entities, relations, labels), and system status.

Two more (`clear_documents`, `clear_cache`) are implemented upstream but
commented out of the `tools/list` declaration, so no conforming MCP client
sees them — their handlers still exist server-side, though, and are
technically reachable via a raw `tools/call` that bypasses discovery. Not
changed in this fork; noted here so it isn't a surprise.

## Security notes

- Destructive tools (`delete_document`, `delete_entity`, `delete_relation`,
  `update_entity`, `update_relation`) are active and reachable by anyone
  holding a valid OAuth token for your instance. Neither `supergateway`
  nor `mcp-auth-proxy` filter individual tools — access control is
  all-or-nothing at the connection level.
- `mcp-auth-proxy`'s password mode is designed for a single owner, not
  multi-tenant access. If you need per-user accounts, point it at Google/
  GitHub/OIDC instead (`mcp-auth-proxy` supports all three — see its own
  [docs](https://sigbit.github.io/mcp-auth-proxy/)) rather than sharing
  one password.
- Rotating the password: generate a new one, set `MCP_AUTH_PASSWORD`,
  redeploy. Already-issued OAuth tokens for existing connections keep
  working — only *new* client authorizations need the new password.

## Credits

- [desimpkins/daniel-lightrag-mcp](https://github.com/desimpkins/daniel-lightrag-mcp) —
  the original MCP tool this is forked from (MIT).
- [supercorp-ai/supergateway](https://github.com/supercorp-ai/supergateway) —
  stdio ⇄ streamable-HTTP bridge.
- [sigbit/mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) —
  drop-in OAuth 2.1 gateway for MCP servers.
- [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — the knowledge
  base this all sits in front of.

## License

MIT — see `LICENSE`. Original copyright Daniel Simpkins; changes in this
fork by Alex Bic.

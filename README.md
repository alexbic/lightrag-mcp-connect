# lightrag-mcp-connect

**English** | [Русский](README.ru.md) | [Español](README.es.md)

MCP access to a [LightRAG](https://github.com/HKUDS/LightRAG) knowledge
base that works both ways: **locally** via `uvx` (zero setup, direct
file access) when Claude runs on the same machine as LightRAG, and
**remotely** via an OAuth-protected gateway (see `deploy/`) when you
want claude.ai on your phone, or any other device, to reach the same
knowledge base. Same tool, same `tools/list`, same code — just pick the
transport that matches where you're calling from. Nothing stops you
from running both at once (see "Using both at once" below).

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

This fork adds two alternatives:

- **`file_url`** — a public http(s) link (e.g. an uploaded attachment or
  artifact URL). The MCP server fetches it itself; nothing about the file
  ever touches the calling agent's context or output tokens. Protected
  against SSRF: requests to private, loopback, link-local, and reserved
  addresses (including the cloud metadata endpoint) are rejected before
  any connection is attempted, and fetches are capped at 50MB.
- **`file_content`** (base64) + `filename` — for when there's no URL.
  The content travels inside the tool call itself, no shared filesystem
  needed. Should be produced by a script/tool call (e.g. a shell `base64`
  command), not the model transcribing it token by token — besides the
  token cost, a large inline base64 blob can also trip content-safety
  classifiers that flag it as obfuscated data.

`file_path` is kept for same-machine / local-stdio setups, where it's
free (the server reads the file directly, nothing to fetch or encode).

```jsonc
// Before (only works if the MCP server can read this path itself):
{ "file_path": "/some/local/path.pdf" }

// After — pick whichever applies, in this order of preference:
{ "file_url": "https://example.com/report.pdf" }
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
lightrag-mcp-connect (this repo, via uvx-from-git)  ──  the actual MCP tool
  ▼  X-API-Key
your LightRAG instance
```

`lightrag-mcp-gw` is never exposed directly — only `lightrag-mcp-auth`
faces the internet, and it forwards to the gateway over a private docker
network.

## Local usage (zero setup)

If Claude runs on the same machine as your LightRAG instance (Claude
Desktop or Claude Code on your own laptop, talking to a local or
same-host LightRAG), skip all of the above — no OAuth gateway, no
`deploy/`, no `git clone`, no virtualenv. Point an MCP client straight
at this package via [`uv`](https://docs.astral.sh/uv/)'s `uvx`:

```json
{
  "mcpServers": {
    "lightrag": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alexbic/lightrag-mcp-connect.git@v1.0.0",
        "lightrag-mcp-connect"
      ],
      "env": {
        "LIGHTRAG_BASE_URL": "http://localhost:9621",
        "LIGHTRAG_API_KEY": "your-lightrag-api-key"
      }
    }
  }
}
```

`uvx` installs `uv` once (`curl -LsSf https://astral.sh/uv/install.sh |
sh`), then fetches this package into an isolated, cached environment on
first run — no manual clone or `pip install` step, ever. Running this
way also gets you `file_path` support for free: the MCP server reads
files directly off your disk, since it's the same machine as the tool
calling it.

The URL above pins the latest stable release (`@v1.0.0` — see
[Releases](https://github.com/alexbic/lightrag-mcp-connect/releases)
for what's available). Drop the `@v1.0.0` entirely to always track
`main` instead, or replace it with a commit SHA if you need to pin
something more specific.

## Deploying (remote)

You need an existing LightRAG instance already running somewhere
reachable from this stack. Don't have one? See
[HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) — this repo only adds
the remote-MCP layer on top.

```bash
git clone https://github.com/alexbic/lightrag-mcp-connect.git
cd lightrag-mcp-connect/deploy
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

## Connecting Claude (remote)

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

## Using both at once

Nothing stops you from configuring both setups side by side, under
different server names, in the same MCP client:

```json
{
  "mcpServers": {
    "lightrag-local": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alexbic/lightrag-mcp-connect.git@v1.0.0",
        "lightrag-mcp-connect"
      ],
      "env": {
        "LIGHTRAG_BASE_URL": "http://localhost:9621",
        "LIGHTRAG_API_KEY": "your-lightrag-api-key"
      }
    }
  }
}
```

plus the remote gateway added as a custom connector (see "Connecting
Claude (remote)" above), under a different name. Use `lightrag-local`
when you want `file_path` to work against files that are actually on
your machine; use the remote connector from your phone, or from any
device that isn't where LightRAG's files live. It's the same knowledge
base and the same MCP tool code either way — just two different
transports (stdio vs. streamable-HTTP-over-OAuth) pointed at it.

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

- `upload_document`'s `file_url` makes the MCP server fetch a URL the
  caller supplies. It rejects private/loopback/link-local/reserved
  addresses (including the cloud metadata endpoint) before connecting,
  and caps fetches at 50MB — a baseline SSRF defense, not a complete one
  (it doesn't protect against DNS rebinding between the check and the
  request). Anyone with a valid OAuth token can use it to make your
  server issue outbound HTTP requests to arbitrary public URLs.
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
fork by Alexander Bikmukhametov.

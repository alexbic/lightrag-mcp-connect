# LightRAG MCP

Query and update a LightRAG knowledge graph via MCP tools.

## Modes

**Simple** (default): Direct connection, single workspace, all data visible.

**Gateway** (`LIGHTRAG_GATEWAY_URL` set): Routes through workspace gateway. Env key `LIGHTRAG_API_KEY` = superadmin (sees all workspaces + admin tools). Pass `api_key` argument to target a specific workspace.

## File Naming Convention

Use `{workspace}__{description}.md` format.
Examples: `main__project-notes.md`, `example__architecture.md`

## Session Metadata

Start each file with: `[Agent | Channel | Date | Project]`

- Agent: Claude Code / Telegram Bot / Desktop / API
- Channel: Source of user request (Terminal:Mac, Web, WhatsApp)
- Date: YYYY-MM-DD
- Project: Project name or "general"

## What to Save (priority order)

1. Decisions + reasons (why, not just what)
2. Problems + solutions (bug → cause → fix)
3. Technical lessons (non-obvious findings, workarounds)
4. Project facts (stack, architecture)
5. User preferences (style, tools)

**Do NOT save**: source code (git), logs, conversational filler.

## Tools

### Documents
- `upload_document` — create/replace document (forms: `file_path`, `file_url`, `filename+text_content`)
- `get_documents` — list all
- `get_documents_paginated` — paginated (page_size 10-100)
- `delete_document` — delete by ID
- `append_text` — append to end (requires MCP-managed content)

### Query
- `query_text` — query graph (mode: naive/local/global/hybrid/mix)

### Graph
- `get_knowledge_graph` — full graph
- `get_graph_labels` — labels
- `check_entity_exists` — check entity
- `update_entity` / `update_relation` — update
- `delete_entity` / `delete_relation` — delete

### System
- `get_health` — server health
- `get_pipeline_status` — document processing status
- `get_track_status` — track status (track_id)
- `get_document_status_counts` — status counts

### Admin (gateway mode, admin key only)
- `create_workspace` — create workspace + key
- `issue_key` — issue additional key
- `revoke_key` — revoke key
- `rotate_key` — rotate key (issue + revoke)

## Operation Semantics

- `upload_document` with same filename = full replacement (delete old + upload new). In gateway mode, writes to workspace determined by key.
- `append_text` only works for documents whose source is MCP-managed (after first `upload_document` with `text_content`). For others, use `update_document` once.

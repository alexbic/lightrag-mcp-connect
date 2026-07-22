# LightRAG MCP Instructions

Use this MCP as working memory and a project knowledge base.

## Connection Mode

- This client works through a remote MCP endpoint.
- Do not assume access to the user's local filesystem.

## File Handling

- Use the document file name as the identifier plus the provided text content.
- Use `file_url` only if the client really supports that transfer mode.
- Do not request a local filesystem path in remote mode.

## File Naming

- File names should describe the document content.
- Do not encode workspace, role, or transport mode into the document file name.
- Prefer plain names such as `project-notes.md`, `deployment-decisions.md`, or `working-preferences.md`.

## Session Metadata

Start each long-term memory document with:

`[Client | Channel | YYYY-MM-DD | Project]`

## Memory Value Pyramid

Only save information that belongs to one of these levels:

1. Decisions and reasons.
2. Problems, causes, and fixes.
3. Ideas and plans.
4. Facts about projects, architecture, or infrastructure.
5. User working preferences.

If the information does not fit one of these levels, do not save it.

## Pre-write Filter

Before writing a document, check:

1. Does it fit one of the 5 pyramid levels?
2. Will it still be useful in a future session weeks or months later?
3. Is it durable knowledge rather than one-off noise?

If any answer is "no", do not write it to memory.

## Do Not Save

- Raw source code.
- Logs or stack traces without a lesson.
- Heartbeat or status messages.
- One-off operational updates without long-term value.
- News, weather, market prices, or short-lived alerts.
- Conversational filler.

## Common Operations

- Use `query_text` with `mode="hybrid"` or `mode="local"` to read context.
- Use `upload_document(filename, text_content)` for new text memory.
- Use `append_text` only for MCP-managed text documents.
- Use `update_document` for full replacement of an existing logical record.

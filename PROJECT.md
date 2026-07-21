# Project: LightRAG MCP Gateway

**Slug:** `lightrag-mcp-gateway`  
**Created:** 2026-07-21  
**Status:** active

## Goal
Provide a public LightRAG MCP connector plus workspace gateway stack with managed workspaces, API-key isolation, and a clean path from single-user LightRAG to multi-workspace agent memory.

## Stakeholders
- Maintainers: repository maintainers
- Users: self-hosters, teams, and agents connecting to LightRAG through MCP
- Operators: agents or humans maintaining deployments of this repository

## Current Focus
Ship the **managed backend mode** first:

- `gateway` owns workspace routing and starts official `lightrag-server` child processes per active workspace.
- `mcp` remains the MCP connector layer.
- External LightRAG proxy mode is explicitly later work.

## Repository Layout
- `gateway/` — workspace registry, key management, managed LightRAG process gateway.
- `mcp/` — MCP connector package source.
- `deploy/` — generic Compose examples.
- `AGENTS.md` — required project-reading protocol for agents.
- `TECH_STACK.md` — stack, tools, commands, and operational assumptions.
- `SPEC.md` — source of truth for behavior.
- `PLAN.md` — active implementation plan.
- `ROADMAP.md` — milestones.
- `BACKLOG.md` — tasks and deferred work.
- `STATUS.md` — current state and verification.

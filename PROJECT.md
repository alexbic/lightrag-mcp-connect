# Project: LightRAG MCP Gateway

**Slug:** `lightrag-mcp-gateway`  
**Created:** 2026-07-21  
**PM:** @alexbic  
**Status:** active

## Goal
Provide the public LightRAG MCP connector plus workspace gateway stack with managed workspaces, API-key isolation, and a clean path from single-user legacy LightRAG to multi-workspace agent memory.

## Stakeholders
- Owner: @alexbic
- Users: @alexbic, family/project agents, future public self-hosters
- Operators: Codex/Claude agents working through this repository

## Current Focus
Ship the **managed backend mode** first:

- `gateway` owns workspace routing and starts official `lightrag-server` child processes per active workspace.
- `mcp` remains the MCP connector layer.
- External LightRAG proxy mode is explicitly later work.

## Repository Layout
- `gateway/` — workspace registry, key management, managed LightRAG process gateway.
- `mcp/` — MCP connector package.
- `deploy/` — production and generic Compose files.
- `AGENTS.md` — required project-reading protocol for agents.
- `TECH_STACK.md` — stack, tools, commands, and operational assumptions.
- `SPEC.md` — source of truth for behavior.
- `PLAN.md` — active implementation plan.
- `ROADMAP.md` — milestones.
- `BACKLOG.md` — tasks and deferred work.
- `STATUS.md` — current state and verification.


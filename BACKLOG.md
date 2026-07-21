# Backlog

## To Do
- [ ] @devops: Prepare deployment example switch to gateway-mode — DoD: MCP uses `LIGHTRAG_GATEWAY_URL`, not `LIGHTRAG_BASE_URL`.
- [ ] @qa: Verify admin tools through MCP — DoD: admin sees tools; normal workspace key does not.
- [ ] @docs: Document first-time setup flow for managed backend mode — DoD: README has copy/paste path.

## In Progress
- [ ] @backend: Managed backend hardening and project readability cleanup — started 2026-07-21.

## Review
- [ ] @qa: Review `LIGHTRAG_ADMIN_KEY` naming and docs for first-time user clarity.

## Done
- [x] @backend: Merge `feature/workspace-gateway` into `main` — DoD: clean merge completed on `main`, relevant checks passed, and project state files updated.
- [x] @backend: Reconcile `main` release direction before merging `feature/workspace-gateway` — DoD: decision recorded that `main` resumes the managed gateway track while legacy users pin `v1.1.1`, then rerun safe merge pre-checks.
- [x] @backend: Resolve pending public `lightrag-mcp-connect` `feature/workspace-gateway` changes — DoD: no dirty worktree, tests pass.
- [x] @backend: Decide release tag for managed gateway-aware MCP — DoD: tag exists and deployment examples can pin it.
- [x] @docs: Add recoverable task-state protocol for agents — DoD: `AGENTS.md` explains how to record start, progress, blockers, checks, and handoff.
- [x] @docs: Add task decomposition rule for agents — DoD: `AGENTS.md` requires sizing tasks and splitting large work into independently testable items.
- [x] @docs: Add skills/tools check rule for agents — DoD: `AGENTS.md` tells agents to use applicable existing skills/tools or propose a reusable skill for repeated workflows.
- [x] @docs: Add fix-and-verification loop rule for agents — DoD: `AGENTS.md` requires classify/fix/verify/repeat before declaring a blocker.
- [x] @docs: Add Decision Gate rule for maintainer-level blockers — DoD: `AGENTS.md` requires options, risks, recommendation, and recorded decision before irreversible work.
- [x] @docs: Refresh README and Compose release pins to `v1.3.0` — DoD: tag exists and affected Compose files validate.
- [x] @qa: Re-run merge readiness verification after dependency access was available — DoD: MCP checks, gateway checks, Compose config, and Docker build pass.
- [x] @docs: Add public privacy/bootstrap rules to agent instructions.
- [x] @backend: Document secret hygiene for public repo instructions.
- [x] @backend: Deploy managed workspace gateway.
- [x] @backend: Create and verify example workspace isolation.
- [x] @backend: Rename project layout to `gateway/app` and `mcp/app`.
- [x] @backend: Replace bootstrap admin env wording with `LIGHTRAG_ADMIN_KEY`.
- [x] @devops: Run local Docker build for `gateway/Dockerfile` — image builds from repo root.

## Bugs from QA
- [x] @qa: Local Docker build was not verified before because Docker daemon was unavailable — fixed 2026-07-21.

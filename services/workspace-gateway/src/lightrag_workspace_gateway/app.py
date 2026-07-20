from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .manager import WorkspaceProcessManager
from .registry import WorkspaceRegistry


def upstream_headers(
    incoming: dict[str, str], *, authenticated_workspace_key: bool
) -> dict[str, str]:
    headers = {
        key: value
        for key, value in incoming.items()
        if key.lower()
        not in {"host", "content-length", "x-api-key", "lightrag-workspace"}
    }
    if authenticated_workspace_key:
        headers["X-API-Key"] = os.environ["LIGHTRAG_SERVER_KEY"]
    return headers


def postgres_dsn() -> str:
    return os.getenv("WORKSPACE_DATABASE_URL") or (
        "postgresql://{user}:{password}@{host}:{port}/{database}".format(
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.getenv("POSTGRES_HOST", "lightrag-db"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            database=os.getenv("POSTGRES_DATABASE", "lightrag"),
        )
    )


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.registry = await WorkspaceRegistry.connect(
            postgres_dsn(), os.environ["WORKSPACE_KEY_PEPPER"]
        )
        await app.state.registry.bootstrap_admin_key(
            os.getenv("WORKSPACE_BOOTSTRAP_ADMIN_KEY", "")
        )
        app.state.manager = WorkspaceProcessManager(
            first_port=int(os.getenv("WORKSPACE_FIRST_PORT", "9700")),
            max_instances=int(os.getenv("WORKSPACE_MAX_ACTIVE", "16")),
            working_root=os.getenv("WORKING_DIR", "/app/data/rag_storage"),
            input_root=os.getenv("INPUT_DIR", "/app/data/inputs"),
        )
        yield
        await app.state.manager.close()
        await app.state.registry.close()

    app = FastAPI(title="LightRAG Workspace Gateway", lifespan=lifespan)

    def require_admin(value: str | None) -> None:
        expected = os.environ["WORKSPACE_ADMIN_KEY"]
        if value is None or not __import__("hmac").compare_digest(value, expected):
            raise HTTPException(401, "invalid workspace admin key")

    @app.get("/_workspaces")
    async def list_workspaces(x_admin_key: str | None = Header(None)):
        require_admin(x_admin_key)
        return {"workspaces": await app.state.registry.list_workspaces()}

    @app.post("/_workspaces/{slug}", status_code=201)
    async def create_workspace(
        slug: str, request: Request, x_admin_key: str | None = Header(None)
    ):
        require_admin(x_admin_key)
        body = await request.json() if request.headers.get("content-length") else {}
        try:
            workspace = await app.state.registry.create_workspace(
                slug, body.get("display_name")
            )
            token = await app.state.registry.issue_key(workspace)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"workspace": workspace, "api_key": token, "shown_once": True}

    @app.post("/_workspaces/{slug}/keys", status_code=201)
    async def issue_key(slug: str, x_admin_key: str | None = Header(None)):
        require_admin(x_admin_key)
        try:
            token = await app.state.registry.issue_key(slug)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"workspace": slug, "api_key": token, "shown_once": True}

    @app.delete("/_keys/{prefix}")
    async def revoke_key(prefix: str, x_admin_key: str | None = Header(None)):
        require_admin(x_admin_key)
        return {"revoked": await app.state.registry.revoke_key(prefix)}

    @app.post("/_keys/admin", status_code=201)
    async def issue_admin_key(x_admin_key: str | None = Header(None)):
        require_admin(x_admin_key)
        token = await app.state.registry.issue_key(None, admin=True)
        return {"workspace": "*", "api_key": token, "shown_once": True}

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def proxy(
        path: str,
        request: Request,
        x_api_key: str | None = Header(None),
        lightrag_workspace: str | None = Header(None),
    ):
        # Browser/JWT and unauthenticated liveness traffic retain legacy main behavior.
        workspace = "main"
        if x_api_key:
            principal = await app.state.registry.resolve(x_api_key)
            if principal is None:
                raise HTTPException(401, "invalid workspace key")
            if principal.is_admin:
                workspace = lightrag_workspace or "main"
                try:
                    workspace = app.state.registry.validate_slug(workspace)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                if not await app.state.registry.workspace_enabled(workspace):
                    raise HTTPException(404, "workspace is unknown or disabled")
            else:
                if principal.workspace is None:
                    raise HTTPException(500, "workspace key has no workspace")
                workspace = principal.workspace
                if lightrag_workspace and lightrag_workspace != workspace:
                    raise HTTPException(
                        403, "key is not authorized for requested workspace"
                    )
        try:
            instance = await app.state.manager.acquire(workspace)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        url = f"http://127.0.0.1:{instance.port}/{path}"
        if request.url.query:
            url += f"?{request.url.query}"
        headers = upstream_headers(
            dict(request.headers), authenticated_workspace_key=bool(x_api_key)
        )
        # Never turn an unauthenticated public request into an authenticated
        # one. JWT/browser traffic is forwarded as-is; only a validated
        # workspace key is exchanged for the private child-server key.
        try:
            upstream = await app.state.manager.client.send(
                app.state.manager.client.build_request(
                    request.method, url, headers=headers, content=await request.body()
                ),
                stream=True,
            )
        except Exception:
            app.state.manager.release(instance)
            raise
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in {"content-length", "transfer-encoding", "connection"}
        }

        async def cleanup() -> None:
            await upstream.aclose()
            app.state.manager.release(instance)

        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=response_headers,
            background=BackgroundTask(cleanup),
        )

    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "lightrag_workspace_gateway.app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "9621")),
        workers=1,
    )

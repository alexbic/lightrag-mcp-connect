"""App-level tests for registry-based admin authorization.

Verifies that admin API routes (``/_workspaces``, ``/_keys/*``) authorize
via the registry's ``is_admin`` flag — not a static env secret. A key is
admin iff ``registry.resolve()`` returns a principal with ``is_admin=true``.

Uses httpx ``ASGITransport`` directly against the FastAPI app with a stub
registry, so no postgres is required.
"""

from __future__ import annotations

import httpx
import pytest

from lightrag_workspace_gateway.app import create_app
from lightrag_workspace_gateway.registry import Principal


class _StubRegistry:
    """Minimal registry stub: resolves a fixed key→principal map."""

    def __init__(self, resolves: dict[str, Principal | None]):
        self._resolves = resolves

    async def resolve(self, token: str) -> Principal | None:
        return self._resolves.get(token)

    async def list_workspaces(self) -> list[dict]:
        return [{"slug": "main", "display_name": "Main"}]


@pytest.fixture
def app_with_registry():
    """Create the gateway app with a stub registry (no lifespan, no postgres)."""
    admin = Principal(key_id=1, workspace=None, is_admin=True)
    user = Principal(key_id=2, workspace="ossi", is_admin=False)
    registry = _StubRegistry(
        resolves={"admin-key": admin, "user-key": user, "dead-key": None}
    )
    app = create_app()
    app.state.registry = registry
    return app


@pytest.mark.asyncio
async def test_admin_key_authorizes(app_with_registry):
    """An is_admin=true key reaches the admin endpoint (200)."""
    transport = httpx.ASGITransport(app=app_with_registry)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.get("/_workspaces", headers={"X-Admin-Key": "admin-key"})
    assert resp.status_code == 200
    assert resp.json()["workspaces"][0]["slug"] == "main"


@pytest.mark.asyncio
async def test_workspace_key_rejected(app_with_registry):
    """A regular workspace key (is_admin=false) is rejected (401)."""
    transport = httpx.ASGITransport(app=app_with_registry)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.get("/_workspaces", headers={"X-Admin-Key": "user-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_key_rejected(app_with_registry):
    """No X-Admin-Key at all is rejected (401)."""
    transport = httpx.ASGITransport(app=app_with_registry)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.get("/_workspaces")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_key_rejected(app_with_registry):
    """A key that resolves to no principal is rejected (401)."""
    transport = httpx.ASGITransport(app=app_with_registry)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.get("/_workspaces", headers={"X-Admin-Key": "dead-key"})
    assert resp.status_code == 401

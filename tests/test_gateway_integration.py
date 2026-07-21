"""Integration tests for workspace-aware MCP modes (Phase 5).

Tests mock the gateway endpoints (no real docker required) but verify the
full request flow: mode detection, per-request api key routing, admin tools,
and dynamic tools/list filtering.
"""

import os
from unittest.mock import patch

import httpx
import pytest

from lightrag_mcp_connect.client import (
    LightRAGClient,
    set_request_api_key,
    reset_request_api_key,
)
from lightrag_mcp_connect.server import handle_list_tools


def make_mock_async_client(mock_handler, timeout=30.0):
    """Build a drop-in replacement for ``httpx.AsyncClient``.

    Returns ``(mock_class, real_client)``. ``mock_class`` is a class whose
    instances act as async context managers that yield a single real
    ``httpx.AsyncClient`` wired to a ``MockTransport`` running *mock_handler*.
    The real client is constructed once, *before* any patching, so there is no
    recursion when ``httpx.AsyncClient`` is later replaced by ``mock_class``.

    Both ``tool_handlers`` and ``server`` resolve ``httpx`` through a plain
    ``import httpx`` (module namespace), so ``patch("httpx.AsyncClient", cls)``
    covers call sites in both modules.
    """

    real_client = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler), timeout=timeout
    )

    class _MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return real_client

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    return _MockAsyncClient, real_client


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment vars and global state before each test."""
    original_env = {}
    for key in [
        "LIGHTRAG_GATEWAY_URL",
        "LIGHTRAG_API_KEY",
        "LIGHTRAG_BASE_URL",
        "WORKSPACE_ADMIN_KEY",
    ]:
        original_env[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]
    yield
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]

    # Reset globals in server.py module (singleton client + admin cache)
    import sys
    server_module = sys.modules['lightrag_mcp_connect.server']
    server_module.lightrag_client = None
    server_module._is_admin_cache = None


class TestGatewayModeDetection:
    """Test that mode detection switches between direct and gateway URLs."""

    @pytest.mark.asyncio
    async def test_simple_mode_no_gateway_url(self):
        """Simple mode: no LIGHTRAG_GATEWAY_URL → direct LightRAG URL."""
        os.environ["LIGHTRAG_API_KEY"] = "test-key"
        from lightrag_mcp_connect.server import _get_lightrag_client

        client = _get_lightrag_client()
        assert client.base_url == "http://localhost:9621"  # default direct

    @pytest.mark.asyncio
    async def test_gateway_mode_sets_base_url(self):
        """Gateway mode: LIGHTRAG_GATEWAY_URL set → gateway URL."""
        os.environ["LIGHTRAG_GATEWAY_URL"] = "http://gateway:9621"
        os.environ["LIGHTRAG_API_KEY"] = "admin-key"
        from lightrag_mcp_connect.server import _get_lightrag_client

        client = _get_lightrag_client()
        assert client.base_url == "http://gateway:9621"
        # Singleton cache: second call returns same client
        client2 = _get_lightrag_client()
        assert client is client2


class TestPerRequestApiKeyRouting:
    """Test per-request api_key routing via ContextVar."""

    def test_set_and_reset_request_api_key(self):
        """ContextVar set/reset works correctly."""
        token = set_request_api_key("lr_test_ABC123")
        assert token is not None
        from lightrag_mcp_connect.client import _REQUEST_API_KEY

        assert _REQUEST_API_KEY.get() == "lr_test_ABC123"
        reset_request_api_key(token)
        assert _REQUEST_API_KEY.get() is None

    @pytest.mark.asyncio
    async def test_per_request_key_override_in_http_request(self):
        """Per-request api_key overrides client default in HTTP calls."""
        captured = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured["x-api-key"] = request.headers.get("x-api-key")
            return httpx.Response(200, json={"status": "healthy"})

        client = LightRAGClient(
            base_url="http://test", api_key="env-default-key", timeout=30.0
        )
        client.client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            headers={"X-API-Key": "env-default-key"},
        )

        # 1. No override → client default
        await client.get_health()
        assert captured["x-api-key"] == "env-default-key"

        # 2. Override → per-request key wins
        token = set_request_api_key("lr_workspace_TEST")
        try:
            await client.get_health()
            assert captured["x-api-key"] == "lr_workspace_TEST"
        finally:
            reset_request_api_key(token)

        # 3. After reset → back to client default
        await client.get_health()
        assert captured["x-api-key"] == "env-default-key"


class TestAdminToolsGatewayCalls:
    """Test admin tools call correct gateway endpoints with X-Admin-Key."""

    @pytest.mark.asyncio
    async def test_create_workspace_calls_gateway_correctly(self):
        """create_workspace POSTs to /_workspaces/{slug} with X-Admin-Key."""
        os.environ["LIGHTRAG_GATEWAY_URL"] = "http://gateway:9621"
        os.environ["LIGHTRAG_API_KEY"] = "env-admin-key"

        captured = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["x-admin-key"] = request.headers.get("x-admin-key")
            return httpx.Response(
                200,
                json={
                    "workspace": "testproj",
                    "api_key": "lr_testproj_ABC123...",
                    "shown_once": True,
                },
            )

        mock_client_cls, real_client = make_mock_async_client(mock_handler)
        try:
            with patch("httpx.AsyncClient", mock_client_cls):
                from lightrag_mcp_connect.tool_handlers import create_workspace

                result = await create_workspace(
                    {"slug": "testproj", "display_name": "Test Project"}, None
                )

            assert captured["url"] == "http://gateway:9621/_workspaces/testproj"
            assert captured["method"] == "POST"
            assert captured["x-admin-key"] == "env-admin-key"
            assert result["api_key"] == "lr_testproj_ABC123..."
        finally:
            await real_client.aclose()

    @pytest.mark.asyncio
    async def test_revoke_key_calls_gateway_correctly(self):
        """revoke_key DELETEs to /_keys/{prefix} with X-Admin-Key."""
        os.environ["LIGHTRAG_GATEWAY_URL"] = "http://gateway:9621"
        os.environ["LIGHTRAG_API_KEY"] = "env-admin-key"

        captured = {}

        def mock_handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["x-admin-key"] = request.headers.get("x-admin-key")
            return httpx.Response(200, json={"revoked": 1})

        mock_client_cls, real_client = make_mock_async_client(mock_handler)
        try:
            with patch("httpx.AsyncClient", mock_client_cls):
                from lightrag_mcp_connect.tool_handlers import revoke_key

                result = await revoke_key({"prefix": "lr_main_ABC123"}, None)

            assert captured["url"] == "http://gateway:9621/_keys/lr_main_ABC123"
            assert captured["method"] == "DELETE"
            assert captured["x-admin-key"] == "env-admin-key"
            assert result["revoked"] == 1
        finally:
            await real_client.aclose()


class TestDynamicToolsListFiltering:
    """Test admin tools are dynamically filtered based on gateway admin check."""

    @pytest.mark.asyncio
    async def test_admin_tools_hidden_in_simple_mode(self):
        """Simple mode (no gateway) → admin tools not exposed."""
        os.environ["LIGHTRAG_API_KEY"] = "any-key"
        # No LIGHTRAG_GATEWAY_URL set

        tools = await handle_list_tools()
        tool_names = {tool.name for tool in tools}

        admin_tools = {"create_workspace", "issue_key", "revoke_key", "rotate_key"}
        assert not admin_tools.intersection(
            tool_names
        ), "Admin tools should be hidden in simple mode"

    @pytest.mark.asyncio
    async def test_admin_tools_hidden_without_admin_key(self):
        """Gateway mode but key is not admin → admin tools hidden."""
        os.environ["LIGHTRAG_GATEWAY_URL"] = "http://gateway:9621"
        os.environ["LIGHTRAG_API_KEY"] = "regular-user-key"  # Not admin

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "invalid workspace admin key"})

        mock_client_cls, real_client = make_mock_async_client(mock_handler, timeout=5.0)
        try:
            with patch("httpx.AsyncClient", mock_client_cls):
                tools = await handle_list_tools()
                tool_names = {tool.name for tool in tools}

            admin_tools = {"create_workspace", "issue_key", "revoke_key", "rotate_key"}
            assert not admin_tools.intersection(
                tool_names
            ), "Admin tools should be hidden when key is not admin"
        finally:
            await real_client.aclose()

    @pytest.mark.asyncio
    async def test_admin_tools_exposed_for_admin_key(self):
        """Gateway mode with admin key → admin tools exposed."""
        os.environ["LIGHTRAG_GATEWAY_URL"] = "http://gateway:9621"
        os.environ["LIGHTRAG_API_KEY"] = "superadmin-key"

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"workspaces": [{"slug": "main", "display_name": "Main"}]}
            )

        mock_client_cls, real_client = make_mock_async_client(mock_handler, timeout=5.0)
        try:
            with patch("httpx.AsyncClient", mock_client_cls):
                tools = await handle_list_tools()
                tool_names = {tool.name for tool in tools}

            admin_tools = {"create_workspace", "issue_key", "revoke_key", "rotate_key"}
            assert admin_tools.issubset(
                tool_names
            ), "Admin tools should be exposed for admin key"
        finally:
            await real_client.aclose()

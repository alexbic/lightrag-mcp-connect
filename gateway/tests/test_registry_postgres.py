import os

import pytest

from lightrag_workspace_gateway.registry import WorkspaceRegistry


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_DSN"), reason="TEST_POSTGRES_DSN is not configured"
)
async def test_registry_lifecycle_against_postgres() -> None:
    registry = await WorkspaceRegistry.connect(
        os.environ["TEST_POSTGRES_DSN"], "integration-pepper-value-32-chars"
    )
    try:
        assert await registry.workspace_enabled("main")
        assert await registry.create_workspace("ossi", "Ossi") == "ossi"
        token = await registry.issue_key("ossi")
        principal = await registry.resolve(token)
        assert principal is not None
        assert principal.workspace == "ossi"
        assert principal.is_admin is False
        assert await registry.resolve("wrong-key") is None

        admin_token = await registry.issue_key(None, admin=True)
        admin = await registry.resolve(admin_token)
        assert admin is not None and admin.is_admin is True

        assert await registry.revoke_key(token[:18]) == 1
        assert await registry.resolve(token) is None
    finally:
        await registry.close()

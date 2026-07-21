import pytest

from lightrag_workspace_gateway.app import upstream_headers
from lightrag_workspace_gateway.manager import WorkspaceProcessManager
from lightrag_workspace_gateway.registry import WorkspaceRegistry


def test_slug_validation() -> None:
    assert WorkspaceRegistry.validate_slug("Example") == "example"
    assert WorkspaceRegistry.validate_slug("project-42") == "project-42"
    with pytest.raises(ValueError):
        WorkspaceRegistry.validate_slug("../escape")


def test_key_hash_is_keyed_and_deterministic() -> None:
    registry = WorkspaceRegistry(None, "p" * 32)  # type: ignore[arg-type]
    assert registry.hash_key("secret") == registry.hash_key("secret")
    assert registry.hash_key("secret") != registry.hash_key("other")
    assert "secret" not in registry.hash_key("secret")


def test_upstream_key_is_added_only_after_workspace_auth(monkeypatch) -> None:
    monkeypatch.setenv("LIGHTRAG_SERVER_KEY", "internal-only")
    incoming = {
        "host": "public.example",
        "X-API-Key": "client-key",
        "Authorization": "Bearer jwt",
    }
    public = upstream_headers(incoming, authenticated_workspace_key=False)
    authenticated = upstream_headers(incoming, authenticated_workspace_key=True)

    assert "X-API-Key" not in public
    assert public["Authorization"] == "Bearer jwt"
    assert authenticated["X-API-Key"] == "internal-only"
    assert "client-key" not in authenticated.values()


def test_main_preserves_legacy_storage_workspace(monkeypatch) -> None:
    monkeypatch.delenv("WORKSPACE_MAIN_STORAGE_NAME", raising=False)
    assert WorkspaceProcessManager.storage_workspace_for("main") == ""
    assert WorkspaceProcessManager.storage_workspace_for("example") == "example"

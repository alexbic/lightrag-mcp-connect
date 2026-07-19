"""
Test workspace header in client requests.
"""
import os
import sys
import json
import asyncio
from unittest.mock import AsyncMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lightrag_mcp_connect.client import LightRAGClient

async def test_workspace_header():
    """Test that workspace header is added correctly."""

    # Test 1: Client without workspace (default)
    client = LightRAGClient(
        base_url="http://localhost:9621",
        api_key="test-key"
    )
    assert "LIGHTRAG-WORKSPACE" not in client.client.headers
    print("✓ Test 1: Default client - no workspace header")

    # Test 2: Client with specific workspace
    client = LightRAGClient(
        base_url="http://localhost:9621",
        api_key="test-key",
        workspace="ossi"
    )
    assert client.client.headers.get("LIGHTRAG-WORKSPACE") == "ossi"
    print("✓ Test 2: Ossi workspace - header added correctly")

    # Test 3: Admin client (workspace="*" - should NOT send header)
    client = LightRAGClient(
        base_url="http://localhost:9621",
        api_key="test-key",
        workspace="*"
    )
    assert "LIGHTRAG-WORKSPACE" not in client.client.headers
    print("✓ Test 3: Admin workspace - no header (all workspaces)")

    print("\n✅ All client workspace tests passed!")

if __name__ == "__main__":
    asyncio.run(test_workspace_header())
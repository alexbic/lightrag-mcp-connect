"""
Test workspace authorization logic.
"""
import os
import sys
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lightrag_mcp_connect.server import load_workspace_keys, get_workspace_from_key

def test_workspace_resolution():
    """Test workspace resolution from API keys."""

    # Test 1: Load empty keys
    os.environ['MCP_WORKSPACE_KEYS'] = '{}'
    keys = load_workspace_keys()
    print(f"✓ Test 1: Load empty keys - {keys}")
    assert keys == {}

    # Test 2: Load sample keys
    sample_keys = {
        "*": "sk-admin-abc123",
        "ossi": "sk-ossi-def456",
        "project_x": "sk-proj-ghi789"
    }
    os.environ['MCP_WORKSPACE_KEYS'] = json.dumps(sample_keys)
    keys = load_workspace_keys()
    print(f"✓ Test 2: Load sample keys - {len(keys)} keys loaded")
    assert len(keys) == 3

    # Test 3: Resolve admin key
    workspace = get_workspace_from_key("sk-admin-abc123")
    print(f"✓ Test 3: Resolve admin key - workspace: {workspace}")
    assert workspace == "*"

    # Test 4: Resolve ossi key
    workspace = get_workspace_from_key("sk-ossi-def456")
    print(f"✓ Test 4: Resolve ossi key - workspace: {workspace}")
    assert workspace == "ossi"

    # Test 5: Resolve project_x key
    workspace = get_workspace_from_key("sk-proj-ghi789")
    print(f"✓ Test 5: Resolve project_x key - workspace: {workspace}")
    assert workspace == "project_x"

    # Test 6: Invalid key
    workspace = get_workspace_from_key("invalid-key")
    print(f"✓ Test 6: Invalid key - workspace: {workspace}")
    assert workspace is None

    print("\n✅ All workspace tests passed!")

if __name__ == "__main__":
    test_workspace_resolution()
"""
Pytest configuration and fixtures for lightrag-mcp-connect tests.
"""

import pytest
import asyncio
from typing import Dict, Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
import httpx

from lightrag_mcp_connect.client import LightRAGClient
from lightrag_mcp_connect.server import server


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for testing."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    return mock_client


@pytest.fixture
def lightrag_client(mock_httpx_client):
    """Create a LightRAG client with mocked HTTP client."""
    client = LightRAGClient(base_url="http://localhost:9621")
    client.client = mock_httpx_client
    return client


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    def _create_response(status_code: int = 200, json_data: Dict[str, Any] = None, text: str = ""):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text
        response.raise_for_status = MagicMock()
        
        if status_code >= 400:
            error = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=response
            )
            response.raise_for_status.side_effect = error
        
        return response
    
    return _create_response


@pytest.fixture
def mock_streaming_response():
    """Create a mock streaming HTTP response."""
    def _create_streaming_response(chunks: list, status_code: int = 200):
        async def aiter_text():
            for chunk in chunks:
                yield chunk
        
        response = MagicMock()
        response.status_code = status_code
        response.aiter_text = aiter_text
        response.raise_for_status = MagicMock()
        
        if status_code >= 400:
            error = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=response
            )
            response.raise_for_status.side_effect = error
        
        return response
    
    return _create_streaming_response


# Sample test data fixtures
@pytest.fixture
def sample_text_document():
    """Sample text document for testing."""
    return {
        "title": "Test Document",
        "content": "This is a test document content.",
        "metadata": {"author": "test", "category": "testing"}
    }


@pytest.fixture
def sample_insert_response():
    """Sample insert response for testing."""
    return {
        "id": "doc_123",
        "status": "success",
        "message": "Document inserted successfully"
    }


@pytest.fixture
def sample_query_response():
    """Sample query response for testing."""
    return {
        "query": "test query",
        "results": [
            {
                "document_id": "doc_123",
                "snippet": "This is a test snippet",
                "score": 0.95,
                "metadata": {"relevance": "high"}
            }
        ],
        "total_results": 1,
        "processing_time": 0.123,
        "context": "Test context information"
    }


@pytest.fixture
def sample_documents_response():
    """Sample documents response for testing."""
    return {
        "documents": [
            {
                "id": "doc_123",
                "title": "Test Document",
                "status": "processed",
                "created_at": "2024-01-01T00:00:00Z",
                "metadata": {"author": "test"}
            }
        ],
        "total": 1
    }


@pytest.fixture
def sample_graph_response():
    """Sample knowledge graph response for testing."""
    return {
        "entities": [
            {
                "id": "entity_123",
                "name": "Test Entity",
                "type": "concept",
                "properties": {"description": "A test entity"},
                "created_at": "2024-01-01T00:00:00Z"
            }
        ],
        "relations": [
            {
                "id": "rel_123",
                "source_entity": "entity_123",
                "target_entity": "entity_456",
                "type": "related_to",
                "properties": {"strength": "high"},
                "weight": 0.8
            }
        ],
        "total_entities": 1,
        "total_relations": 1
    }


@pytest.fixture
def sample_health_response():
    """Sample health response for testing."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime": 3600.0,
        "database_status": "connected",
        "cache_status": "active",
        "message": "All systems operational"
    }


@pytest.fixture
def sample_pipeline_status_response():
    """Sample pipeline status response for testing."""
    return {
        "status": "running",
        "progress": 75.5,
        "current_task": "processing documents",
        "message": "Pipeline is running normally"
    }


@pytest.fixture
def sample_status_counts_response():
    """Sample status counts response for testing."""
    return {
        "pending": 5,
        "processing": 2,
        "processed": 100,
        "failed": 1,
        "total": 108
    }
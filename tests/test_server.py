"""
Unit tests for MCP server functionality.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from mcp.types import CallToolRequest, CallToolResult, ListToolsRequest

from lightrag_mcp_remote.server import (
    handle_list_tools, 
    handle_call_tool,
    _validate_tool_arguments,
    _create_success_response,
    _create_error_response
)
from lightrag_mcp_remote.client import (
    LightRAGError, 
    LightRAGConnectionError, 
    LightRAGValidationError,
    LightRAGAPIError
)


class TestServerToolListing:
    """Test MCP server tool listing functionality."""
    
    @pytest.mark.asyncio
    async def test_handle_list_tools(self):
        """Test that all 22 tools are listed correctly."""
        result = await handle_list_tools()
        
        assert len(result.tools) == 22
        
        # Check that all expected tools are present
        tool_names = [tool.name for tool in result.tools]
        
        # Document Management Tools (8 tools)
        document_tools = [
            "insert_text", "insert_texts", "upload_document", "scan_documents",
            "get_documents", "get_documents_paginated", "delete_document", "clear_documents"
        ]
        
        # Query Tools (2 tools)
        query_tools = ["query_text", "query_text_stream"]
        
        # Knowledge Graph Tools (7 tools)
        graph_tools = [
            "get_knowledge_graph", "get_graph_labels", "check_entity_exists",
            "update_entity", "update_relation", "delete_entity", "delete_relation"
        ]
        
        # System Management Tools (5 tools)
        system_tools = [
            "get_pipeline_status", "get_track_status", "get_document_status_counts",
            "clear_cache", "get_health"
        ]
        
        all_expected_tools = document_tools + query_tools + graph_tools + system_tools
        
        for tool_name in all_expected_tools:
            assert tool_name in tool_names, f"Tool {tool_name} not found in listed tools"
        
        # Verify tool schemas have required properties
        for tool in result.tools:
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputSchema')
            assert tool.description is not None
            assert tool.inputSchema is not None


class TestToolArgumentValidation:
    """Test tool argument validation functionality."""
    
    def test_validate_required_arguments_success(self):
        """Test successful validation of required arguments."""
        # Test tools with required arguments
        _validate_tool_arguments("insert_text", {"text": "test content"})
        _validate_tool_arguments("query_text", {"query": "test query"})
        _validate_tool_arguments("delete_document", {"document_id": "doc_123"})
        _validate_tool_arguments("update_entity", {"entity_id": "ent_123", "properties": {}})
    
    def test_validate_missing_required_arguments(self):
        """Test validation failure for missing required arguments."""
        with pytest.raises(LightRAGValidationError, match="Missing required arguments"):
            _validate_tool_arguments("insert_text", {})
        
        with pytest.raises(LightRAGValidationError, match="Missing required arguments"):
            _validate_tool_arguments("query_text", {})
        
        with pytest.raises(LightRAGValidationError, match="Missing required arguments"):
            _validate_tool_arguments("update_entity", {"entity_id": "ent_123"})
    
    def test_validate_pagination_arguments(self):
        """Test validation of pagination arguments."""
        # Valid pagination
        _validate_tool_arguments("get_documents_paginated", {"page": 1, "page_size": 10})
        
        # Invalid page number
        with pytest.raises(LightRAGValidationError, match="Page must be a positive integer"):
            _validate_tool_arguments("get_documents_paginated", {"page": 0, "page_size": 10})
        
        # Invalid page size
        with pytest.raises(LightRAGValidationError, match="Page size must be an integer"):
            _validate_tool_arguments("get_documents_paginated", {"page": 1, "page_size": 101})
    
    def test_validate_query_mode(self):
        """Test validation of query mode arguments."""
        # Valid modes
        for mode in ["naive", "local", "global", "hybrid"]:
            _validate_tool_arguments("query_text", {"query": "test", "mode": mode})
        
        # Invalid mode
        with pytest.raises(LightRAGValidationError, match="Invalid query mode"):
            _validate_tool_arguments("query_text", {"query": "test", "mode": "invalid"})


class TestResponseCreation:
    """Test response creation utilities."""
    
    def test_create_success_response(self):
        """Test creation of success responses."""
        test_result = {"status": "success", "data": "test"}
        response = _create_success_response(test_result, "test_tool")
        
        assert isinstance(response, CallToolResult)
        assert not response.isError
        assert len(response.content) == 1
        
        # Parse the JSON content
        content_text = response.content[0].text
        parsed_content = json.loads(content_text)
        assert parsed_content == test_result
    
    def test_create_error_response_lightrag_error(self):
        """Test creation of error responses for LightRAG errors."""
        error = LightRAGValidationError("Test validation error", status_code=400)
        response = _create_error_response(error, "test_tool")
        
        assert isinstance(response, CallToolResult)
        assert response.isError
        assert len(response.content) == 1
        
        # Parse the JSON content
        content_text = response.content[0].text
        parsed_content = json.loads(content_text)
        
        assert parsed_content["tool"] == "test_tool"
        assert parsed_content["error_type"] == "LightRAGValidationError"
        assert parsed_content["message"] == "Test validation error"
    
    def test_create_error_response_generic_error(self):
        """Test creation of error responses for generic errors."""
        error = ValueError("Generic error")
        response = _create_error_response(error, "test_tool")
        
        assert isinstance(response, CallToolResult)
        assert response.isError
        assert len(response.content) == 1
        
        # Parse the JSON content
        content_text = response.content[0].text
        parsed_content = json.loads(content_text)
        
        assert parsed_content["tool"] == "test_tool"
        assert parsed_content["error_type"] == "ValueError"
        assert parsed_content["message"] == "Generic error"


@pytest.mark.asyncio
class TestDocumentManagementTools:
    """Test document management MCP tools."""
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_insert_text_success(self, mock_client):
        """Test successful text insertion."""
        # Setup mock
        mock_result = {"id": "doc_123", "status": "success"}
        mock_client.insert_text = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "insert_text", "arguments": {"text": "test content"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.insert_text.assert_called_once_with("test content")
        
        # Parse response
        content = json.loads(result.content[0].text)
        assert content == mock_result
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_insert_texts_success(self, mock_client):
        """Test successful multiple text insertion."""
        # Setup mock
        mock_result = {"id": "batch_123", "status": "success"}
        mock_client.insert_texts = AsyncMock(return_value=mock_result)
        
        # Create request
        texts = [{"content": "text 1"}, {"content": "text 2"}]
        request = CallToolRequest(
            method="tools/call",
            params={"name": "insert_texts", "arguments": {"texts": texts}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.insert_texts.assert_called_once_with(texts)
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_upload_document_success(self, mock_client):
        """Test successful document upload."""
        # Setup mock
        mock_result = {"filename": "test.txt", "status": "uploaded"}
        mock_client.upload_document = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "upload_document", "arguments": {"file_path": "/path/to/file.txt"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.upload_document.assert_called_once_with("/path/to/file.txt")
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_scan_documents_success(self, mock_client):
        """Test successful document scanning."""
        # Setup mock
        mock_result = {"scanned": 5, "new_documents": ["doc1.txt", "doc2.txt"]}
        mock_client.scan_documents = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "scan_documents", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.scan_documents.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_documents_success(self, mock_client):
        """Test successful document retrieval."""
        # Setup mock
        mock_result = {"documents": [{"id": "doc_123", "title": "Test"}], "total": 1}
        mock_client.get_documents = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_documents", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_documents.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_documents_paginated_success(self, mock_client):
        """Test successful paginated document retrieval."""
        # Setup mock
        mock_result = {
            "documents": [{"id": "doc_123", "title": "Test"}],
            "pagination": {"page": 1, "page_size": 10, "total_pages": 1}
        }
        mock_client.get_documents_paginated = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_documents_paginated", "arguments": {"page": 1, "page_size": 10}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_documents_paginated.assert_called_once_with(1, 10)
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_delete_document_success(self, mock_client):
        """Test successful document deletion."""
        # Setup mock
        mock_result = {"deleted": True, "document_id": "doc_123"}
        mock_client.delete_document = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "delete_document", "arguments": {"document_id": "doc_123"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.delete_document.assert_called_once_with("doc_123")
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_clear_documents_success(self, mock_client):
        """Test successful document clearing."""
        # Setup mock
        mock_result = {"cleared": True, "count": 10}
        mock_client.clear_documents = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "clear_documents", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.clear_documents.assert_called_once()


@pytest.mark.asyncio
class TestQueryTools:
    """Test query MCP tools."""
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_query_text_success(self, mock_client):
        """Test successful text query."""
        # Setup mock
        mock_result = {
            "query": "test query",
            "results": [{"document_id": "doc_123", "snippet": "test snippet", "score": 0.95}],
            "total_results": 1
        }
        mock_client.query_text = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={
                "name": "query_text", 
                "arguments": {"query": "test query", "mode": "hybrid", "only_need_context": False}
            }
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.query_text.assert_called_once_with(
            "test query", mode="hybrid", only_need_context=False
        )
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_query_text_stream_success(self, mock_client):
        """Test successful streaming text query."""
        # Setup mock - async generator with proper signature
        async def mock_stream(query, mode="hybrid", only_need_context=False):
            yield "chunk 1"
            yield "chunk 2"
            yield "chunk 3"
        
        # Setup mock client
        mock_client.query_text_stream = mock_stream
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={
                "name": "query_text_stream", 
                "arguments": {"query": "test query", "mode": "hybrid"}
            }
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        
        # Parse response to check streaming result
        content = json.loads(result.content[0].text)
        assert "streaming_response" in content
        assert content["streaming_response"] == "chunk 1chunk 2chunk 3"


@pytest.mark.asyncio
class TestKnowledgeGraphTools:
    """Test knowledge graph MCP tools."""
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_knowledge_graph_success(self, mock_client):
        """Test successful knowledge graph retrieval."""
        # Setup mock
        mock_result = {
            "entities": [{"id": "ent_123", "name": "Test Entity"}],
            "relations": [{"id": "rel_123", "source_entity": "ent_123", "target_entity": "ent_456"}],
            "total_entities": 1,
            "total_relations": 1
        }
        mock_client.get_knowledge_graph = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_knowledge_graph", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_knowledge_graph.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_graph_labels_success(self, mock_client):
        """Test successful graph labels retrieval."""
        # Setup mock
        mock_result = {
            "entity_labels": ["Person", "Organization", "Location"],
            "relation_labels": ["works_for", "located_in", "related_to"]
        }
        mock_client.get_graph_labels = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_graph_labels", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_graph_labels.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_check_entity_exists_success(self, mock_client):
        """Test successful entity existence check."""
        # Setup mock
        mock_result = {"exists": True, "entity_name": "Test Entity", "entity_id": "ent_123"}
        mock_client.check_entity_exists = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "check_entity_exists", "arguments": {"entity_name": "Test Entity"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.check_entity_exists.assert_called_once_with("Test Entity")
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_update_entity_success(self, mock_client):
        """Test successful entity update."""
        # Setup mock
        mock_result = {"updated": True, "entity_id": "ent_123"}
        mock_client.update_entity = AsyncMock(return_value=mock_result)
        
        # Create request
        properties = {"name": "Updated Entity", "type": "concept"}
        request = CallToolRequest(
            method="tools/call",
            params={
                "name": "update_entity", 
                "arguments": {"entity_id": "ent_123", "properties": properties}
            }
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.update_entity.assert_called_once_with("ent_123", properties)
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_update_relation_success(self, mock_client):
        """Test successful relation update."""
        # Setup mock
        mock_result = {"updated": True, "relation_id": "rel_123"}
        mock_client.update_relation = AsyncMock(return_value=mock_result)
        
        # Create request
        properties = {"type": "strongly_related", "weight": 0.9}
        request = CallToolRequest(
            method="tools/call",
            params={
                "name": "update_relation", 
                "arguments": {"relation_id": "rel_123", "properties": properties}
            }
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.update_relation.assert_called_once_with("rel_123", properties)
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_delete_entity_success(self, mock_client):
        """Test successful entity deletion."""
        # Setup mock
        mock_result = {"deleted": True, "id": "ent_123", "type": "entity"}
        mock_client.delete_entity = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "delete_entity", "arguments": {"entity_id": "ent_123"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.delete_entity.assert_called_once_with("ent_123")
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_delete_relation_success(self, mock_client):
        """Test successful relation deletion."""
        # Setup mock
        mock_result = {"deleted": True, "id": "rel_123", "type": "relation"}
        mock_client.delete_relation = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "delete_relation", "arguments": {"relation_id": "rel_123"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.delete_relation.assert_called_once_with("rel_123")


@pytest.mark.asyncio
class TestSystemManagementTools:
    """Test system management MCP tools."""
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_pipeline_status_success(self, mock_client):
        """Test successful pipeline status retrieval."""
        # Setup mock
        mock_result = {
            "status": "running",
            "progress": 75.5,
            "current_task": "processing documents"
        }
        mock_client.get_pipeline_status = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_pipeline_status", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_pipeline_status.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_track_status_success(self, mock_client):
        """Test successful track status retrieval."""
        # Setup mock
        mock_result = {
            "track_id": "track_123",
            "status": "completed",
            "progress": 100.0
        }
        mock_client.get_track_status = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_track_status", "arguments": {"track_id": "track_123"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_track_status.assert_called_once_with("track_123")
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_document_status_counts_success(self, mock_client):
        """Test successful document status counts retrieval."""
        # Setup mock
        mock_result = {
            "pending": 5,
            "processing": 2,
            "processed": 100,
            "failed": 1,
            "total": 108
        }
        mock_client.get_document_status_counts = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_document_status_counts", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_document_status_counts.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_clear_cache_success(self, mock_client):
        """Test successful cache clearing."""
        # Setup mock
        mock_result = {"cleared": True, "cache_type": "all"}
        mock_client.clear_cache = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "clear_cache", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.clear_cache.assert_called_once()
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_get_health_success(self, mock_client):
        """Test successful health check."""
        # Setup mock
        mock_result = {
            "status": "healthy",
            "version": "1.0.0",
            "uptime": 3600.0,
            "database_status": "connected"
        }
        mock_client.get_health = AsyncMock(return_value=mock_result)
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "get_health", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify
        assert not result.isError
        mock_client.get_health.assert_called_once()


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in MCP tools."""
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_tool_validation_error(self, mock_client):
        """Test handling of validation errors."""
        # Create request with missing required argument
        request = CallToolRequest(
            method="tools/call",
            params={"name": "insert_text", "arguments": {}}  # Missing 'text' argument
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify error response
        assert result.isError
        content = json.loads(result.content[0].text)
        assert content["error_type"] == "LightRAGValidationError"
        assert "Missing required arguments" in content["message"]
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_client_connection_error(self, mock_client):
        """Test handling of connection errors."""
        # Setup mock to raise connection error
        mock_client.insert_text = AsyncMock(
            side_effect=LightRAGConnectionError("Connection failed")
        )
        
        # Create request
        request = CallToolRequest(
            method="tools/call",
            params={"name": "insert_text", "arguments": {"text": "test"}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify error response
        assert result.isError
        content = json.loads(result.content[0].text)
        assert content["error_type"] == "LightRAGConnectionError"
        assert "Connection failed" in content["message"]
    
    @patch('lightrag_mcp_remote.server.lightrag_client')
    async def test_unknown_tool_error(self, mock_client):
        """Test handling of unknown tool calls."""
        # Create request for non-existent tool
        request = CallToolRequest(
            method="tools/call",
            params={"name": "unknown_tool", "arguments": {}}
        )
        
        # Execute
        result = await handle_call_tool(request)
        
        # Verify error response
        assert result.isError
        assert "Unknown tool: unknown_tool" in result.content[0].text
    
    @patch('lightrag_mcp_remote.server.lightrag_client', None)
    async def test_client_initialization_error(self):
        """Test handling of client initialization errors."""
        with patch('lightrag_mcp_remote.server.LightRAGClient', side_effect=Exception("Init failed")):
            # Create request
            request = CallToolRequest(
                method="tools/call",
                params={"name": "get_health", "arguments": {}}
            )
            
            # Execute
            result = await handle_call_tool(request)
            
            # Verify error response
            assert result.isError
            content = json.loads(result.content[0].text)
            assert content["error_type"] == "LightRAGConnectionError"
            assert "Failed to initialize LightRAG client" in content["message"]
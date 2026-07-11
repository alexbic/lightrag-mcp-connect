"""
Unit tests for Pydantic models.
"""

import pytest
from typing import Dict, Any
from pydantic import ValidationError

from lightrag_mcp_connect.models import (
    # Enums
    DocStatus, QueryMode, PipelineStatus,
    # Common models
    TextDocument, PaginationInfo,
    # Request models
    InsertTextRequest, InsertTextsRequest, QueryRequest, EntityUpdateRequest,
    RelationUpdateRequest, DeleteDocRequest, DocumentsRequest, ClearCacheRequest,
    # Response models
    InsertResponse, ScanResponse, UploadResponse, DocumentsResponse, PaginatedDocsResponse,
    DeleteDocByIdResponse, ClearDocumentsResponse, QueryResponse, QueryResult,
    GraphResponse, EntityInfo, RelationInfo, LabelsResponse, EntityExistsResponse,
    EntityUpdateResponse, RelationUpdateResponse, DeletionResult,
    PipelineStatusResponse, TrackStatusResponse, StatusCountsResponse,
    ClearCacheResponse, HealthResponse
)


class TestEnums:
    """Test enum definitions."""
    
    def test_doc_status_enum(self):
        """Test DocStatus enum values."""
        assert DocStatus.PENDING == "pending"
        assert DocStatus.PROCESSING == "processing"
        assert DocStatus.PROCESSED == "processed"
        assert DocStatus.FAILED == "failed"
        assert DocStatus.DELETED == "deleted"
    
    def test_query_mode_enum(self):
        """Test QueryMode enum values."""
        assert QueryMode.NAIVE == "naive"
        assert QueryMode.LOCAL == "local"
        assert QueryMode.GLOBAL == "global"
        assert QueryMode.HYBRID == "hybrid"
    
    def test_pipeline_status_enum(self):
        """Test PipelineStatus enum values."""
        assert PipelineStatus.IDLE == "idle"
        assert PipelineStatus.RUNNING == "running"
        assert PipelineStatus.COMPLETED == "completed"
        assert PipelineStatus.FAILED == "failed"


class TestCommonModels:
    """Test common model definitions."""
    
    def test_text_document_valid(self):
        """Test valid TextDocument creation."""
        doc = TextDocument(
            title="Test Document",
            content="This is test content",
            metadata={"author": "test", "category": "testing"}
        )
        
        assert doc.title == "Test Document"
        assert doc.content == "This is test content"
        assert doc.metadata["author"] == "test"
    
    def test_text_document_minimal(self):
        """Test TextDocument with minimal required fields."""
        doc = TextDocument(content="Test content")
        
        assert doc.title is None
        assert doc.content == "Test content"
        assert doc.metadata is None
    
    def test_text_document_missing_content(self):
        """Test TextDocument validation error for missing content."""
        with pytest.raises(ValidationError) as exc_info:
            TextDocument(title="Test")
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("content",)
        assert errors[0]["type"] == "missing"
    
    def test_pagination_info_valid(self):
        """Test valid PaginationInfo creation."""
        pagination = PaginationInfo(
            page=2,
            page_size=20,
            total_pages=5,
            total_items=100
        )
        
        assert pagination.page == 2
        assert pagination.page_size == 20
        assert pagination.total_pages == 5
        assert pagination.total_items == 100
    
    def test_pagination_info_defaults(self):
        """Test PaginationInfo with default values."""
        pagination = PaginationInfo()
        
        assert pagination.page == 1
        assert pagination.page_size == 10
        assert pagination.total_pages is None
        assert pagination.total_items is None
    
    def test_pagination_info_validation_errors(self):
        """Test PaginationInfo validation errors."""
        # Test invalid page number
        with pytest.raises(ValidationError) as exc_info:
            PaginationInfo(page=0)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "greater_than_equal" for error in errors)
        
        # Test invalid page size
        with pytest.raises(ValidationError) as exc_info:
            PaginationInfo(page_size=0)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "greater_than_equal" for error in errors)
        
        # Test page size too large
        with pytest.raises(ValidationError) as exc_info:
            PaginationInfo(page_size=101)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "less_than_equal" for error in errors)


class TestRequestModels:
    """Test request model definitions."""
    
    def test_insert_text_request_valid(self):
        """Test valid InsertTextRequest creation."""
        request = InsertTextRequest(
            title="Test Title",
            content="Test content"
        )
        
        assert request.title == "Test Title"
        assert request.content == "Test content"
    
    def test_insert_text_request_minimal(self):
        """Test InsertTextRequest with minimal fields."""
        request = InsertTextRequest(content="Test content")
        
        assert request.title is None
        assert request.content == "Test content"
    
    def test_insert_text_request_missing_content(self):
        """Test InsertTextRequest validation error."""
        with pytest.raises(ValidationError) as exc_info:
            InsertTextRequest(title="Test")
        
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("content",)
    
    def test_insert_texts_request_valid(self):
        """Test valid InsertTextsRequest creation."""
        texts = [
            TextDocument(content="Text 1"),
            TextDocument(content="Text 2", title="Title 2")
        ]
        request = InsertTextsRequest(texts=texts)
        
        assert len(request.texts) == 2
        assert request.texts[0].content == "Text 1"
        assert request.texts[1].title == "Title 2"
    
    def test_query_request_valid(self):
        """Test valid QueryRequest creation."""
        request = QueryRequest(
            query="test query",
            mode=QueryMode.HYBRID,
            only_need_context=True,
            stream=False
        )
        
        assert request.query == "test query"
        assert request.mode == QueryMode.HYBRID
        assert request.only_need_context is True
        assert request.stream is False
    
    def test_query_request_defaults(self):
        """Test QueryRequest with default values."""
        request = QueryRequest(query="test query")
        
        assert request.query == "test query"
        assert request.mode == QueryMode.HYBRID
        assert request.only_need_context is False
        assert request.stream is False
    
    def test_entity_update_request_valid(self):
        """Test valid EntityUpdateRequest creation."""
        properties = {"name": "Updated Entity", "type": "concept"}
        request = EntityUpdateRequest(
            entity_id="ent_123",
            properties=properties
        )
        
        assert request.entity_id == "ent_123"
        assert request.properties == properties
    
    def test_relation_update_request_valid(self):
        """Test valid RelationUpdateRequest creation."""
        properties = {"type": "strongly_related", "weight": 0.9}
        request = RelationUpdateRequest(
            relation_id="rel_123",
            properties=properties
        )
        
        assert request.relation_id == "rel_123"
        assert request.properties == properties
    
    def test_documents_request_valid(self):
        """Test valid DocumentsRequest creation."""
        request = DocumentsRequest(
            page=2,
            page_size=20,
            status_filter=DocStatus.PROCESSED
        )
        
        assert request.page == 2
        assert request.page_size == 20
        assert request.status_filter == DocStatus.PROCESSED
    
    def test_documents_request_defaults(self):
        """Test DocumentsRequest with default values."""
        request = DocumentsRequest()
        
        assert request.page == 1
        assert request.page_size == 10
        assert request.status_filter is None


class TestResponseModels:
    """Test response model definitions."""
    
    def test_insert_response_valid(self):
        """Test valid InsertResponse creation."""
        response = InsertResponse(
            id="doc_123",
            status="success",
            message="Document inserted successfully"
        )
        
        assert response.id == "doc_123"
        assert response.status == "success"
        assert response.message == "Document inserted successfully"
    
    def test_scan_response_valid(self):
        """Test valid ScanResponse creation."""
        response = ScanResponse(
            scanned=5,
            new_documents=["doc1.txt", "doc2.txt"],
            message="Scan completed"
        )
        
        assert response.scanned == 5
        assert len(response.new_documents) == 2
        assert response.message == "Scan completed"
    
    def test_scan_response_defaults(self):
        """Test ScanResponse with default values."""
        response = ScanResponse(scanned=0)
        
        assert response.scanned == 0
        assert response.new_documents == []
        assert response.message is None
    
    def test_query_result_valid(self):
        """Test valid QueryResult creation."""
        result = QueryResult(
            document_id="doc_123",
            snippet="This is a test snippet",
            score=0.95,
            metadata={"relevance": "high"}
        )
        
        assert result.document_id == "doc_123"
        assert result.snippet == "This is a test snippet"
        assert result.score == 0.95
        assert result.metadata["relevance"] == "high"
    
    def test_query_result_score_validation(self):
        """Test QueryResult score validation."""
        # Valid score
        result = QueryResult(document_id="doc_123", snippet="test", score=0.5)
        assert result.score == 0.5
        
        # Score too low
        with pytest.raises(ValidationError) as exc_info:
            QueryResult(document_id="doc_123", snippet="test", score=-0.1)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "greater_than_equal" for error in errors)
        
        # Score too high
        with pytest.raises(ValidationError) as exc_info:
            QueryResult(document_id="doc_123", snippet="test", score=1.1)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "less_than_equal" for error in errors)
    
    def test_query_response_valid(self):
        """Test valid QueryResponse creation."""
        results = [
            QueryResult(document_id="doc_123", snippet="snippet 1", score=0.9),
            QueryResult(document_id="doc_456", snippet="snippet 2", score=0.8)
        ]
        response = QueryResponse(
            query="test query",
            results=results,
            total_results=2,
            processing_time=0.123,
            context="Test context"
        )
        
        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.total_results == 2
        assert response.processing_time == 0.123
        assert response.context == "Test context"
    
    def test_entity_info_valid(self):
        """Test valid EntityInfo creation."""
        entity = EntityInfo(
            id="ent_123",
            name="Test Entity",
            type="concept",
            properties={"description": "A test entity"},
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-02T00:00:00Z"
        )
        
        assert entity.id == "ent_123"
        assert entity.name == "Test Entity"
        assert entity.type == "concept"
        assert entity.properties["description"] == "A test entity"
        assert entity.created_at == "2024-01-01T00:00:00Z"
    
    def test_relation_info_valid(self):
        """Test valid RelationInfo creation."""
        relation = RelationInfo(
            id="rel_123",
            source_entity="ent_123",
            target_entity="ent_456",
            type="related_to",
            properties={"strength": "high"},
            weight=0.8,
            created_at="2024-01-01T00:00:00Z"
        )
        
        assert relation.id == "rel_123"
        assert relation.source_entity == "ent_123"
        assert relation.target_entity == "ent_456"
        assert relation.type == "related_to"
        assert relation.weight == 0.8
    
    def test_relation_info_weight_validation(self):
        """Test RelationInfo weight validation."""
        # Valid weight
        relation = RelationInfo(
            id="rel_123",
            source_entity="ent_123",
            target_entity="ent_456",
            type="related_to",
            weight=0.5
        )
        assert relation.weight == 0.5
        
        # Weight too low
        with pytest.raises(ValidationError) as exc_info:
            RelationInfo(
                id="rel_123",
                source_entity="ent_123",
                target_entity="ent_456",
                type="related_to",
                weight=-0.1
            )
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "greater_than_equal" for error in errors)
    
    def test_pipeline_status_response_valid(self):
        """Test valid PipelineStatusResponse creation."""
        response = PipelineStatusResponse(
            status=PipelineStatus.RUNNING,
            progress=75.5,
            current_task="processing documents",
            message="Pipeline running normally"
        )
        
        assert response.status == PipelineStatus.RUNNING
        assert response.progress == 75.5
        assert response.current_task == "processing documents"
        assert response.message == "Pipeline running normally"
    
    def test_pipeline_status_response_progress_validation(self):
        """Test PipelineStatusResponse progress validation."""
        # Valid progress
        response = PipelineStatusResponse(status=PipelineStatus.RUNNING, progress=50.0)
        assert response.progress == 50.0
        
        # Progress too low
        with pytest.raises(ValidationError) as exc_info:
            PipelineStatusResponse(status=PipelineStatus.RUNNING, progress=-1.0)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "greater_than_equal" for error in errors)
        
        # Progress too high
        with pytest.raises(ValidationError) as exc_info:
            PipelineStatusResponse(status=PipelineStatus.RUNNING, progress=101.0)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "less_than_equal" for error in errors)
    
    def test_status_counts_response_valid(self):
        """Test valid StatusCountsResponse creation."""
        response = StatusCountsResponse(
            pending=5,
            processing=2,
            processed=100,
            failed=1,
            total=108
        )
        
        assert response.pending == 5
        assert response.processing == 2
        assert response.processed == 100
        assert response.failed == 1
        assert response.total == 108
    
    def test_status_counts_response_defaults(self):
        """Test StatusCountsResponse with default values."""
        response = StatusCountsResponse()
        
        assert response.pending == 0
        assert response.processing == 0
        assert response.processed == 0
        assert response.failed == 0
        assert response.total == 0
    
    def test_status_counts_response_validation(self):
        """Test StatusCountsResponse validation for negative values."""
        with pytest.raises(ValidationError) as exc_info:
            StatusCountsResponse(pending=-1)
        
        errors = exc_info.value.errors()
        assert any(error["type"] == "greater_than_equal" for error in errors)
    
    def test_health_response_valid(self):
        """Test valid HealthResponse creation."""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            uptime=3600.0,
            database_status="connected",
            cache_status="active",
            message="All systems operational"
        )
        
        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.uptime == 3600.0
        assert response.database_status == "connected"
        assert response.cache_status == "active"
        assert response.message == "All systems operational"


class TestModelSerialization:
    """Test model serialization and deserialization."""
    
    def test_text_document_dict_serialization(self):
        """Test TextDocument serialization to dict."""
        doc = TextDocument(
            title="Test Document",
            content="Test content",
            metadata={"author": "test"}
        )
        
        doc_dict = doc.model_dump()
        
        assert doc_dict["title"] == "Test Document"
        assert doc_dict["content"] == "Test content"
        assert doc_dict["metadata"]["author"] == "test"
    
    def test_query_request_dict_serialization(self):
        """Test QueryRequest serialization to dict."""
        request = QueryRequest(
            query="test query",
            mode=QueryMode.HYBRID,
            only_need_context=True
        )
        
        request_dict = request.model_dump()
        
        assert request_dict["query"] == "test query"
        assert request_dict["mode"] == "hybrid"  # Enum serialized as string
        assert request_dict["only_need_context"] is True
        assert request_dict["stream"] is False  # Default value
    
    def test_model_from_dict_deserialization(self):
        """Test model creation from dictionary."""
        data = {
            "id": "doc_123",
            "status": "success",
            "message": "Document inserted"
        }
        
        response = InsertResponse(**data)
        
        assert response.id == "doc_123"
        assert response.status == "success"
        assert response.message == "Document inserted"
    
    def test_nested_model_serialization(self):
        """Test serialization of models with nested models."""
        results = [
            QueryResult(document_id="doc_123", snippet="snippet 1", score=0.9),
            QueryResult(document_id="doc_456", snippet="snippet 2", score=0.8)
        ]
        response = QueryResponse(
            query="test query",
            results=results,
            total_results=2
        )
        
        response_dict = response.model_dump()
        
        assert response_dict["query"] == "test query"
        assert len(response_dict["results"]) == 2
        assert response_dict["results"][0]["document_id"] == "doc_123"
        assert response_dict["results"][0]["score"] == 0.9
        assert response_dict["total_results"] == 2
    
    def test_model_json_serialization(self):
        """Test JSON serialization of models."""
        doc = TextDocument(
            title="Test Document",
            content="Test content"
        )
        
        json_str = doc.model_dump_json()
        
        # Should be valid JSON
        import json
        parsed = json.loads(json_str)
        
        assert parsed["title"] == "Test Document"
        assert parsed["content"] == "Test content"
        assert parsed["metadata"] is None


class TestModelValidationEdgeCases:
    """Test edge cases in model validation."""
    
    def test_empty_string_validation(self):
        """Test validation of empty strings."""
        # Empty content should be allowed (business logic validation elsewhere)
        doc = TextDocument(content="")
        assert doc.content == ""
        
        # Empty query should be allowed (validation in client)
        request = QueryRequest(query="")
        assert request.query == ""
    
    def test_none_values_in_optional_fields(self):
        """Test None values in optional fields."""
        doc = TextDocument(
            title=None,
            content="test",
            metadata=None
        )
        
        assert doc.title is None
        assert doc.content == "test"
        assert doc.metadata is None
    
    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored by default."""
        # This depends on Pydantic configuration
        data = {
            "content": "test content",
            "extra_field": "should be ignored"
        }
        
        doc = TextDocument(**data)
        
        assert doc.content == "test content"
        # extra_field should be ignored (not raise error)
        assert not hasattr(doc, "extra_field")
    
    def test_type_coercion(self):
        """Test automatic type coercion."""
        # String to int coercion for page numbers
        pagination = PaginationInfo(page="2", page_size="10")
        
        assert pagination.page == 2
        assert pagination.page_size == 10
        assert isinstance(pagination.page, int)
        assert isinstance(pagination.page_size, int)
    
    def test_enum_validation(self):
        """Test enum field validation."""
        # Valid enum value
        request = QueryRequest(query="test", mode="hybrid")
        assert request.mode == QueryMode.HYBRID
        
        # Invalid enum value should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(query="test", mode="invalid_mode")
        
        errors = exc_info.value.errors()
        # Check for enum validation error (message may vary between Pydantic versions)
        assert any(
            "Input should be" in str(error["msg"]) or 
            "not a valid enumeration member" in str(error["msg"]) or
            "invalid_mode" in str(error["msg"])
            for error in errors
        )
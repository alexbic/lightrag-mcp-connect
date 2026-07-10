"""
LightRAG API client for MCP server integration.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, AsyncGenerator
import httpx
from .models import (
    # Request models
    InsertTextRequest, InsertTextsRequest, QueryRequest, EntityUpdateRequest,
    RelationUpdateRequest, DeleteDocRequest, DeleteEntityRequest, DeleteRelationRequest,
    DocumentsRequest, ClearCacheRequest, EntityExistsRequest,
    # Response models
    InsertResponse, ScanResponse, UploadResponse, DocumentsResponse, PaginatedDocsResponse,
    DeleteDocByIdResponse, ClearDocumentsResponse, PipelineStatusResponse, TrackStatusResponse,
    StatusCountsResponse, ClearCacheResponse, DeletionResult, QueryResponse, GraphResponse,
    LabelsResponse, EntityExistsResponse, EntityUpdateResponse, RelationUpdateResponse,
    HealthResponse, TextDocument
)


# Custom Exception Hierarchy
class LightRAGError(Exception):
    """Base exception for LightRAG client errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "status_code": self.status_code,
            "response_data": self.response_data
        }


class LightRAGConnectionError(LightRAGError):
    """Exception for connection-related errors."""
    pass


class LightRAGAuthError(LightRAGError):
    """Exception for authentication failures."""
    pass


class LightRAGValidationError(LightRAGError):
    """Exception for input validation errors."""
    pass


class LightRAGAPIError(LightRAGError):
    """Exception for API-specific errors."""
    pass


class LightRAGTimeoutError(LightRAGError):
    """Exception for request timeout errors."""
    pass


class LightRAGServerError(LightRAGError):
    """Exception for server-side errors (5xx status codes)."""
    pass


class LightRAGClient:
    """Client for interacting with LightRAG API."""
    
    def __init__(self, base_url: str = "http://localhost:9621", api_key: Optional[str] = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
            
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers
        )
        
        self.logger.info(f"Initialized LightRAG client with base_url: {self.base_url}")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _map_http_error(self, status_code: int, response_text: str, response_data: Optional[Dict[str, Any]] = None) -> LightRAGError:
        """Map HTTP status codes to appropriate exception types."""
        error_message = f"HTTP {status_code}: {response_text}"
        
        # Try to parse response data for more detailed error information
        parsed_data = response_data or {}
        if response_text:
            try:
                parsed_data = json.loads(response_text)
                if isinstance(parsed_data, dict) and "detail" in parsed_data:
                    error_message = f"HTTP {status_code}: {parsed_data['detail']}"
                elif isinstance(parsed_data, dict) and "message" in parsed_data:
                    error_message = f"HTTP {status_code}: {parsed_data['message']}"
            except json.JSONDecodeError:
                pass
        
        # Map status codes to specific exception types
        if status_code == 400:
            return LightRAGValidationError(f"Bad Request: {error_message}", status_code, parsed_data)
        elif status_code == 401:
            return LightRAGAuthError(f"Unauthorized: {error_message}", status_code, parsed_data)
        elif status_code == 403:
            return LightRAGAuthError(f"Forbidden: {error_message}", status_code, parsed_data)
        elif status_code == 404:
            return LightRAGAPIError(f"Not Found: {error_message}", status_code, parsed_data)
        elif status_code == 408:
            return LightRAGTimeoutError(f"Request Timeout: {error_message}", status_code, parsed_data)
        elif status_code == 422:
            return LightRAGValidationError(f"Validation Error: {error_message}", status_code, parsed_data)
        elif status_code == 429:
            return LightRAGAPIError(f"Rate Limited: {error_message}", status_code, parsed_data)
        elif 500 <= status_code < 600:
            return LightRAGServerError(f"Server Error: {error_message}", status_code, parsed_data)
        else:
            return LightRAGAPIError(error_message, status_code, parsed_data)
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to LightRAG API."""
        url = f"{self.base_url}{endpoint}"
        
        # Log request details
        self.logger.debug(f"Making {method} request to {url}")
        if data:
            self.logger.debug(f"Request data: {json.dumps(data, indent=2)}")
        if params:
            self.logger.debug(f"Request params: {params}")
        
        try:
            if method.upper() == "GET":
                response = await self.client.get(url, params=params)
            elif method.upper() == "POST":
                if files:
                    response = await self.client.post(url, data=data, files=files)
                else:
                    response = await self.client.post(url, json=data)
            elif method.upper() == "DELETE":
                if data:
                    response = await self.client.request("DELETE", url, json=data)
                else:
                    response = await self.client.delete(url)
            else:
                error_msg = f"Unsupported HTTP method: {method}"
                self.logger.error(error_msg)
                raise LightRAGError(error_msg)
            
            # Log response details
            self.logger.debug(f"Response status: {response.status_code}")
            try:
                self.logger.debug(f"Response headers: {dict(response.headers)}")
            except (TypeError, AttributeError):
                # Handle mock objects that don't have proper headers
                self.logger.debug("Response headers: <mock headers>")
            
            response.raise_for_status()
            
            try:
                response_data = response.json()
                self.logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
                self.logger.info(f"Successfully completed {method} request to {endpoint}")
                return response_data
            except json.JSONDecodeError as json_err:
                self.logger.error(f"Failed to parse JSON response: {json_err}")
                self.logger.error(f"Raw response text: {response.text}")
                raise LightRAGAPIError(f"Invalid JSON response from server: {str(json_err)}")
            
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error {e.response.status_code} for {method} {url}: {e.response.text}")
            raise self._map_http_error(e.response.status_code, e.response.text)
        except httpx.ConnectError as e:
            error_msg = f"Connection failed to {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGConnectionError(error_msg)
        except httpx.TimeoutException as e:
            error_msg = f"Request timeout for {method} {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGTimeoutError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Request failed for {method} {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGConnectionError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during {method} request to {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGError(error_msg)
    
    async def _stream_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Make streaming HTTP request to LightRAG API."""
        url = f"{self.base_url}{endpoint}"
        
        # Log streaming request details
        self.logger.debug(f"Making streaming {method} request to {url}")
        if data:
            self.logger.debug(f"Streaming request data: {json.dumps(data, indent=2)}")
        
        try:
            async with self.client.stream(method, url, json=data) as response:
                self.logger.debug(f"Streaming response status: {response.status_code}")
                response.raise_for_status()
                
                chunk_count = 0
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        chunk_count += 1
                        self.logger.debug(f"Received streaming chunk {chunk_count}: {len(chunk)} characters")
                        yield chunk
                
                self.logger.info(f"Successfully completed streaming {method} request to {endpoint}, received {chunk_count} chunks")
                        
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error {e.response.status_code} for streaming {method} {url}: {e.response.text}")
            raise self._map_http_error(e.response.status_code, e.response.text)
        except httpx.ConnectError as e:
            error_msg = f"Connection failed for streaming request to {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGConnectionError(error_msg)
        except httpx.TimeoutException as e:
            error_msg = f"Request timeout for streaming {method} {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGTimeoutError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Request failed for streaming {method} {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGConnectionError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during streaming {method} request to {url}: {str(e)}"
            self.logger.error(error_msg)
            raise LightRAGError(error_msg)
    
    # Document Management Methods (8 methods)
    
    async def insert_text(self, text: str, title: Optional[str] = None) -> InsertResponse:
        """Insert text content into LightRAG."""
        self.logger.info(f"Inserting text document with title: {title}")
        try:
            # Use title as file_source if provided, otherwise use generic name
            file_source = f"{title}.txt" if title else "text_input.txt"
            request_data = InsertTextRequest(text=text, file_source=file_source)
            response_data = await self._make_request("POST", "/documents/text", request_data.model_dump())
            result = InsertResponse(**response_data)
            self.logger.info(f"Successfully inserted text document with ID: {result.id}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to insert text document: {str(e)}")
            if isinstance(e, LightRAGError):
                raise
            # Handle Pydantic validation errors
            if hasattr(e, 'errors') and callable(getattr(e, 'errors')):
                raise LightRAGValidationError(f"Request validation failed: {str(e)}")
            raise LightRAGError(f"Text insertion failed: {str(e)}")
    
    async def insert_texts(self, texts: List[TextDocument]) -> InsertResponse:
        """Insert multiple text documents into LightRAG."""
        # Convert TextDocument objects to strings (content only)
        text_strings = []
        for doc in texts:
            if isinstance(doc, dict):
                # Handle dict input from tests
                text_strings.append(doc.get('content', str(doc)))
            elif hasattr(doc, 'content'):
                # Handle TextDocument objects
                text_strings.append(doc.content)
            else:
                # Handle string input
                text_strings.append(str(doc))
        
        # Create file sources for each text (use generic names to avoid null file_path)
        file_sources = [f"text_input_{i+1}.txt" for i in range(len(text_strings))]
        
        request_data = InsertTextsRequest(texts=text_strings, file_sources=file_sources)
        response_data = await self._make_request("POST", "/documents/texts", request_data.model_dump())
        return InsertResponse(**response_data)
    
    async def upload_document(self, file_path: str) -> UploadResponse:
        """Upload a document file to LightRAG."""
        self.logger.info(f"Uploading document file: {file_path}")
        try:
            # Validate file exists and is readable
            import os
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File does not exist: {file_path}")
            if not os.access(file_path, os.R_OK):
                raise PermissionError(f"File is not readable: {file_path}")
            
            file_size = os.path.getsize(file_path)
            self.logger.debug(f"File size: {file_size} bytes")
            
            with open(file_path, 'rb') as f:
                files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
                response_data = await self._make_request("POST", "/documents/upload", files=files)
                result = UploadResponse(**response_data)
                self.logger.info(f"Successfully uploaded document: {file_path} ({file_size} bytes) - Track ID: {result.track_id}")
                return result
        except FileNotFoundError as e:
            error_msg = f"File not found: {file_path}"
            self.logger.error(error_msg)
            raise LightRAGValidationError(error_msg)
        except PermissionError as e:
            error_msg = f"Permission denied accessing file: {file_path}"
            self.logger.error(error_msg)
            raise LightRAGValidationError(error_msg)
        except Exception as e:
            error_msg = f"Failed to upload file {file_path}: {str(e)}"
            self.logger.error(error_msg)
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(error_msg)
    
    async def upload_document_content(self, content: bytes, filename: str) -> UploadResponse:
        """Upload document content (bytes) directly to LightRAG.

        Unlike upload_document, this doesn't read anything from the local
        filesystem — the caller supplies the file's bytes directly. This is
        the only path that works when the MCP server runs on a different
        machine than the calling agent (e.g. a remote/hosted deployment),
        since there's no shared filesystem to read a path from.
        """
        self.logger.info(f"Uploading document content: {filename} ({len(content)} bytes)")
        try:
            files = {"file": (filename, content, "application/octet-stream")}
            response_data = await self._make_request("POST", "/documents/upload", files=files)
            result = UploadResponse(**response_data)
            self.logger.info(f"Successfully uploaded document content: {filename} ({len(content)} bytes) - Track ID: {result.track_id}")
            return result
        except Exception as e:
            error_msg = f"Failed to upload file content {filename}: {str(e)}"
            self.logger.error(error_msg)
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(error_msg)

    async def scan_documents(self) -> ScanResponse:
        """Scan for new documents in LightRAG."""
        response_data = await self._make_request("POST", "/documents/scan")
        return ScanResponse(**response_data)
    
    async def get_documents(self) -> DocumentsResponse:
        """Retrieve all documents from LightRAG."""
        response_data = await self._make_request("GET", "/documents")
        return DocumentsResponse(**response_data)
    
    async def get_documents_paginated(self, page: int = 1, page_size: int = 10, status_filter: Optional[str] = None) -> PaginatedDocsResponse:
        """Retrieve documents with pagination from LightRAG."""
        request_data = DocumentsRequest(page=page, page_size=page_size, status_filter=status_filter)
        response_data = await self._make_request("POST", "/documents/paginated", request_data.model_dump())
        return PaginatedDocsResponse(**response_data)
    
    async def delete_document(self, document_id: str) -> DeleteDocByIdResponse:
        """Delete a document by ID from LightRAG."""
        request_data = DeleteDocRequest(doc_ids=[document_id])
        response_data = await self._make_request("DELETE", "/documents/delete_document", request_data.model_dump())
        return DeleteDocByIdResponse(**response_data)
    
    async def clear_documents(self) -> ClearDocumentsResponse:
        """Clear all documents from LightRAG."""
        response_data = await self._make_request("DELETE", "/documents")
        return ClearDocumentsResponse(**response_data)
    
    # Query Methods (2 methods)
    
    async def query_text(self, query: str, mode: str = "hybrid", only_need_context: bool = False) -> QueryResponse:
        """Query LightRAG with text."""
        self.logger.info(f"Querying text with mode '{mode}': {query[:100]}{'...' if len(query) > 100 else ''}")
        
        # Validate query parameters
        if not query or not query.strip():
            raise LightRAGValidationError("Query cannot be empty")
        
        valid_modes = ["naive", "local", "global", "hybrid"]
        if mode not in valid_modes:
            raise LightRAGValidationError(f"Invalid query mode '{mode}'. Must be one of: {valid_modes}")
        
        try:
            request_data = QueryRequest(query=query, mode=mode, only_need_context=only_need_context)
            response_data = await self._make_request("POST", "/query", request_data.model_dump())
            result = QueryResponse(**response_data)
            
            result_count = len(result.results) if hasattr(result, 'results') and result.results else 0
            self.logger.info(f"Query completed successfully, returned {result_count} results")
            return result
        except Exception as e:
            self.logger.error(f"Query failed for mode '{mode}': {str(e)}")
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(f"Query operation failed: {str(e)}")
    
    async def query_text_stream(self, query: str, mode: str = "hybrid", only_need_context: bool = False) -> AsyncGenerator[str, None]:
        """Stream query results from LightRAG."""
        # Validate query parameters
        if not query or not query.strip():
            raise LightRAGValidationError("Query cannot be empty")
        
        valid_modes = ["naive", "local", "global", "hybrid"]
        if mode not in valid_modes:
            raise LightRAGValidationError(f"Invalid query mode '{mode}'. Must be one of: {valid_modes}")
        
        self.logger.info(f"Starting streaming query with mode '{mode}': {query[:100]}{'...' if len(query) > 100 else ''}")
        
        try:
            request_data = QueryRequest(query=query, mode=mode, only_need_context=only_need_context, stream=True)
            async for chunk in self._stream_request("POST", "/query/stream", request_data.model_dump()):
                yield chunk
        except Exception as e:
            self.logger.error(f"Streaming query failed for mode '{mode}': {str(e)}")
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(f"Streaming query operation failed: {str(e)}")
    
    # Knowledge Graph Methods (8 methods)
    
    async def get_knowledge_graph(self, label: str = "*") -> GraphResponse:
        """Retrieve the knowledge graph from LightRAG."""
        params = {"label": label}
        response_data = await self._make_request("GET", "/graphs", params=params)
        return GraphResponse(**response_data)
    
    async def get_graph_labels(self) -> LabelsResponse:
        """Get labels for entities and relations in the knowledge graph."""
        response_data = await self._make_request("GET", "/graph/label/list")
        # Server returns a list, but our model expects a dict with labels field
        if isinstance(response_data, list):
            response_data = {"labels": response_data}
        return LabelsResponse(**response_data)
    
    async def check_entity_exists(self, entity_name: str) -> EntityExistsResponse:
        """Check if an entity exists in the knowledge graph."""
        params = {"name": entity_name}
        response_data = await self._make_request("GET", "/graph/entity/exists", params=params)
        return EntityExistsResponse(**response_data)
    
    async def update_entity(self, entity_id: str, properties: Dict[str, Any], entity_name: Optional[str] = None) -> EntityUpdateResponse:
        """Update an entity in the knowledge graph."""
        # Use entity_id as entity_name if not provided
        if entity_name is None:
            entity_name = entity_id
        request_data = EntityUpdateRequest(entity_id=entity_id, entity_name=entity_name, updated_data=properties)
        response_data = await self._make_request("POST", "/graph/entity/edit", request_data.model_dump())
        return EntityUpdateResponse(**response_data)
    
    # async def update_relation(self, relation_id: str, properties: Dict[str, Any], source_id: str = "unknown", target_id: str = "unknown") -> RelationUpdateResponse:
    #     """Update a relation in the knowledge graph."""
    #     request_data = RelationUpdateRequest(relation_id=relation_id, source_id=source_id, target_id=target_id, updated_data=properties)
    #     response_data = await self._make_request("POST", "/graph/relation/edit", request_data.model_dump())
    #     return RelationUpdateResponse(**response_data)

    async def update_relation(self, source_id: str, target_id: str, updated_data: Dict[str, Any]) -> RelationUpdateResponse:
        """Update a relation in the knowledge graph."""
        request_data = RelationUpdateRequest(
            source_id=source_id,
            target_id=target_id,
            updated_data=updated_data
        )
        response_data = await self._make_request("POST", "/graph/relation/edit", request_data.model_dump())
        return RelationUpdateResponse(**response_data)
    
    async def delete_entity(self, entity_id: str, entity_name: Optional[str] = None) -> DeletionResult:
        """Delete an entity from the knowledge graph."""
        # Use entity_id as entity_name if not provided
        if entity_name is None:
            entity_name = entity_id
        request_data = DeleteEntityRequest(entity_id=entity_id, entity_name=entity_name)
        response_data = await self._make_request("DELETE", "/documents/delete_entity", request_data.model_dump())
        return DeletionResult(**response_data)
    
    async def delete_relation(self, relation_id: str, source_entity: str = "unknown", target_entity: str = "unknown") -> DeletionResult:
        """Delete a relation from the knowledge graph."""
        request_data = DeleteRelationRequest(relation_id=relation_id, source_entity=source_entity, target_entity=target_entity)
        response_data = await self._make_request("DELETE", "/documents/delete_relation", request_data.model_dump())
        return DeletionResult(**response_data)
    
    # System Management Methods (4 methods)
    
    async def get_pipeline_status(self) -> PipelineStatusResponse:
        """Get the pipeline status from LightRAG."""
        response_data = await self._make_request("GET", "/documents/pipeline_status")
        return PipelineStatusResponse(**response_data)
    
    async def get_track_status(self, track_id: str) -> TrackStatusResponse:
        """Get the track status for a specific track ID."""
        response_data = await self._make_request("GET", f"/documents/track_status/{track_id}")
        return TrackStatusResponse(**response_data)
    
    async def get_document_status_counts(self) -> StatusCountsResponse:
        """Get document status counts from LightRAG."""
        response_data = await self._make_request("GET", "/documents/status_counts")
        return StatusCountsResponse(**response_data)
    
    async def clear_cache(self, cache_type: Optional[str] = None) -> ClearCacheResponse:
        """Clear LightRAG cache."""
        if cache_type:
            request_data = ClearCacheRequest(cache_type=cache_type).model_dump()
        else:
            request_data = {}
        response_data = await self._make_request("POST", "/documents/clear_cache", request_data)
        return ClearCacheResponse(**response_data)
    
    async def get_health(self) -> HealthResponse:
        """Check LightRAG server health."""
        response_data = await self._make_request("GET", "/health")
        return HealthResponse(**response_data)

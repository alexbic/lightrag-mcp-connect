"""
Daniel LightRAG MCP Server - A Model Context Protocol server for LightRAG integration.
"""

__version__ = "0.1.0"
__author__ = "Daniel Simpkins"
__description__ = "MCP server for LightRAG integration"

from .client import LightRAGClient, LightRAGError
from .server import server
from .models import *

__all__ = [
    "LightRAGClient", 
    "LightRAGError", 
    "server",
    # Enums
    "DocStatus",
    "QueryMode", 
    "PipelineStatus",
    # Common models
    "TextDocument",
    "PaginationInfo",
    "ValidationError",
    "HTTPValidationError",
    # Request models
    "InsertTextRequest",
    "InsertTextsRequest", 
    "DeleteDocRequest",
    "DeleteEntityRequest",
    "DeleteRelationRequest",
    "DocumentsRequest",
    "ClearCacheRequest",
    "QueryRequest",
    "EntityUpdateRequest",
    "RelationUpdateRequest",
    "EntityExistsRequest",
    "LoginRequest",
    # Response models
    "InsertResponse",
    "ScanResponse",
    "UploadResponse",
    "DocumentInfo",
    "DocumentsResponse",
    "PaginatedDocsResponse",
    "DeleteDocByIdResponse",
    "ClearDocumentsResponse",
    "PipelineStatusResponse",
    "TrackStatusResponse",
    "StatusCountsResponse",
    "ClearCacheResponse",
    "DeletionResult",
    "QueryResult",
    "QueryResponse",
    "EntityInfo",
    "RelationInfo",
    "GraphResponse",
    "LabelsResponse",
    "EntityExistsResponse",
    "EntityUpdateResponse",
    "RelationUpdateResponse",
    "HealthResponse",
    "AuthStatusResponse",
    "LoginResponse",
    # Ollama models
    "OllamaVersionResponse",
    "OllamaTagsResponse",
    "OllamaProcessResponse",
    "OllamaGenerateRequest",
    "OllamaChatMessage",
    "OllamaChatRequest",
    # Additional models
    "Body_upload_to_input_dir_documents_upload_post",
    "Body_login_login_post",
    "DocStatusResponse",
    "DocsStatusesResponse",
]

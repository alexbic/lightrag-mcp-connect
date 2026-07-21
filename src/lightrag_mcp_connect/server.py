"""
MCP server for LightRAG integration.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

from .client import (
    LightRAGClient,
    LightRAGError,
    LightRAGConnectionError,
    LightRAGAuthError,
    LightRAGValidationError,
    LightRAGAPIError,
    LightRAGTimeoutError,
    LightRAGServerError,
    set_request_api_key,
    reset_request_api_key,
)
from .tool_handlers import TOOL_HANDLERS

# Configure logging with structured format
logging.basicConfig(
    level=os.getenv("LIGHTRAG_MCP_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class _SensitivePayloadFilter(logging.Filter):
    """Last-line defense against legacy payload-heavy log statements."""

    _blocked_markers = (
        "request content:",
        "request values:",
        "request['",
        "raw arguments:",
        "tool arguments:",
        "arguments to validate:",
        "result content:",
        "result.__dict__:",
        "result.model_dump():",
        "model_dump() result:",
        "dict() result:",
        "content preview:",
        "response preview:",
        "error.to_dict():",
        "error_details:",
        "error context:",
        "response_data:",
        " - query: '",
        " - text: '",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return not any(marker in message for marker in self._blocked_markers)


logger.addFilter(_SensitivePayloadFilter())

# Set specific log levels for different components
logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce httpx noise
logging.getLogger("mcp").setLevel(logging.INFO)

# Initialize the MCP server
server = Server("lightrag-mcp-connect")

# Global client instance
lightrag_client: Optional[LightRAGClient] = None

# Cached admin-key check result for the current env key (probed once per process)
_is_admin_cache: Optional[bool] = None

# LightRAG's own DocumentManager.supported_extensions is computed dynamically
# from its registered parser engines (lightrag/parser/registry.py) — there's
# no static constant to import across the process/container boundary, so
# this is a manual copy of the default-deployment result (no MinerU/Docling
# endpoint configured — verified against LightRAG v1.5.4 source and against
# this instance's own 400 error body). Re-check this list if the operator
# configures MinerU/Docling (adds more suffixes) or upgrades LightRAG.
LIGHTRAG_SUPPORTED_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".mdx",
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".rtf",
        ".odt",
        ".tex",
        ".epub",
        ".html",
        ".htm",
        ".csv",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".log",
        ".conf",
        ".ini",
        ".properties",
        ".sql",
        ".bat",
        ".sh",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".py",
        ".java",
        ".js",
        ".ts",
        ".swift",
        ".go",
        ".rb",
        ".php",
        ".css",
        ".scss",
        ".less",
    }
)

# These are the only formats with a dedicated binary parser in LightRAG
# (pypdf/python-docx/python-pptx/openpyxl) — everything else in
# LIGHTRAG_SUPPORTED_EXTENSIONS is decoded by LightRAG itself as plain
# UTF-8 text, so text_content is equally valid for those. These four
# genuinely need real file bytes; text_content can't represent them.
LIGHTRAG_BINARY_ONLY_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".xlsx"})


def _resolve_allowed_file_path(file_path: str) -> Path:
    """Resolve a local upload path inside the explicitly configured root."""
    configured_root = os.getenv("LIGHTRAG_FILE_PATH_ROOT")
    if not configured_root:
        raise LightRAGValidationError(
            "file_path uploads are disabled. Set LIGHTRAG_FILE_PATH_ROOT to an "
            "allowed directory for a trusted same-host deployment, or use "
            "text_content or file_url."
        )

    try:
        root = Path(configured_root).expanduser().resolve(strict=True)
        candidate = Path(file_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise LightRAGValidationError(f"Invalid file_path configuration: {exc}")
    try:
        candidate.relative_to(root)
    except ValueError:
        raise LightRAGValidationError(
            f"file_path must be inside LIGHTRAG_FILE_PATH_ROOT ({root})"
        )
    if not candidate.is_file():
        raise LightRAGValidationError(f"file_path is not a regular file: {candidate}")
    return candidate


def _validate_tool_arguments(tool_name: str, arguments: Dict[str, Any]) -> None:
    """Validate tool arguments against expected schemas."""
    # Define required arguments for each tool
    required_args = {
        "get_documents_paginated": ["page", "page_size"],
        "delete_document": ["document_id"],
        "query_text": ["query"],
        "query_text_stream": ["query"],
        "check_entity_exists": ["entity_name"],
        "update_entity": ["entity_id", "properties"],
        "update_relation": ["source_id", "target_id", "updated_data"],
        "delete_entity": ["entity_id"],
        "delete_relation": ["relation_id"],
        "get_track_status": ["track_id"],
    }

    # Check if tool requires specific arguments
    if tool_name in required_args:
        missing_args = []
        for required_arg in required_args[tool_name]:
            if required_arg not in arguments:
                missing_args.append(required_arg)

        if missing_args:
            error_msg = f"Missing required arguments for {tool_name}: {missing_args}"
            logger.warning(f"Validation error: {error_msg}")
            raise LightRAGValidationError(error_msg)

    # Additional validation for specific tools
    if tool_name == "upload_document":
        text_content = arguments.get("text_content")
        file_url = arguments.get("file_url")
        file_path = arguments.get("file_path")
        filename = arguments.get("filename")

        supplied_sources = [
            name
            for name, value in (
                ("text_content", text_content),
                ("file_url", file_url),
                ("file_path", file_path),
            )
            if value
        ]
        if not supplied_sources:
            raise LightRAGValidationError(
                "upload_document requires file_path, file_url, or filename + text_content"
            )
        if len(supplied_sources) > 1:
            raise LightRAGValidationError(
                "upload_document accepts exactly one source; got: "
                f"{', '.join(supplied_sources)}"
            )
        if text_content and not filename:
            raise LightRAGValidationError(
                "filename is required when using text_content"
            )

        # Extension checks only make sense when we actually have a filename
        # to check (file_url without a filename override derives its own
        # name from the URL at fetch time, so there's nothing to validate here).
        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in LIGHTRAG_SUPPORTED_EXTENSIONS:
                raise LightRAGValidationError(
                    f"Unsupported file type '{ext}'. LightRAG accepts: "
                    f"{sorted(LIGHTRAG_SUPPORTED_EXTENSIONS)}"
                )
            if text_content and ext in LIGHTRAG_BINARY_ONLY_EXTENSIONS:
                raise LightRAGValidationError(
                    f"text_content can't be used for '{ext}' — LightRAG needs the "
                    f"actual file bytes to parse this format. Use file_url, "
                    f"file_path or file_url instead."
                )

    elif tool_name == "get_documents_paginated":
        page = arguments.get("page", 1)
        page_size = arguments.get("page_size", 10)

        if not isinstance(page, int) or page < 1:
            raise LightRAGValidationError("Page must be a positive integer")
        if not isinstance(page_size, int) or page_size < 1 or page_size > 100:
            raise LightRAGValidationError(
                "Page size must be an integer between 1 and 100"
            )

    elif tool_name == "query_text" or tool_name == "query_text_stream":
        mode = arguments.get("mode", "hybrid")
        valid_modes = ["naive", "local", "global", "hybrid", "mix"]
        if mode not in valid_modes:
            raise LightRAGValidationError(
                f"Invalid query mode '{mode}'. Must be one of: {valid_modes}"
            )

    logger.debug(f"Tool arguments validation passed for {tool_name}")


def _serialize_result(result: Any) -> str:
    """Serialize result to JSON, handling Pydantic models."""
    if hasattr(result, "dict"):
        # Pydantic model
        return json.dumps(result.model_dump(), indent=2)
    elif hasattr(result, "__dict__"):
        # Regular object with __dict__
        return json.dumps(result.__dict__, indent=2)
    else:
        # Fallback to direct serialization
        return json.dumps(result, indent=2)


def _create_success_response(result: Any, tool_name: str) -> CallToolResult:
    """Create standardized MCP success response."""
    logger.info("=" * 60)
    logger.info("CREATING SUCCESS RESPONSE")
    logger.info("=" * 60)
    logger.info(f"SUCCESS RESPONSE INPUT:")
    logger.info(f"  - tool_name: '{tool_name}'")
    logger.info(f"  - result type: {type(result)}")
    logger.info("  - result type: %s", type(result).__name__)

    # Handle Pydantic models properly
    logger.info("RESPONSE SERIALIZATION:")
    if hasattr(result, "model_dump"):
        logger.info("  - Using result.model_dump() (Pydantic v2)")
        try:
            serialized_data = result.model_dump()
            logger.info(f"  - model_dump() result: {serialized_data}")
            response_text = json.dumps(serialized_data, indent=2)
            logger.info(f"  - JSON serialization successful")
        except Exception as e:
            logger.error(f"  - model_dump() failed: {e}")
            response_text = str(result)
    elif hasattr(result, "dict"):
        logger.info("  - Using result.dict() (Pydantic v1)")
        try:
            serialized_data = result.dict()
            logger.info(f"  - dict() result: {serialized_data}")
            response_text = json.dumps(serialized_data, indent=2)
            logger.info(f"  - JSON serialization successful")
        except Exception as e:
            logger.error(f"  - dict() failed: {e}")
            response_text = str(result)
    elif result:
        logger.info("  - Direct JSON serialization")
        try:
            response_text = json.dumps(result, indent=2)
            logger.info(f"  - Direct JSON serialization successful")
        except Exception as e:
            logger.error(f"  - Direct JSON serialization failed: {e}")
            response_text = str(result)
    else:
        logger.info("  - Result is None/empty, using 'Success'")
        response_text = "Success"

    logger.info(f"FINAL RESPONSE TEXT:")
    logger.info(f"  - Length: {len(response_text)} characters")
    logger.info(
        f"  - Content preview: {response_text[:200]}{'...' if len(response_text) > 200 else ''}"
    )

    return CallToolResult(
        content=[TextContent(type="text", text=response_text)], isError=False
    )


def _create_error_response(error: Exception, tool_name: str) -> CallToolResult:
    """Create standardized MCP error response."""
    logger.error("=" * 60)
    logger.error("CREATING ERROR RESPONSE")
    logger.error("=" * 60)
    logger.error(f"ERROR RESPONSE INPUT:")
    logger.error(f"  - tool_name: '{tool_name}'")
    logger.error(f"  - error type: {type(error)}")
    logger.error(f"  - error message: {str(error)}")
    logger.error(f"  - error args: {error.args}")

    # Get full traceback
    import traceback

    logger.error(f"ERROR TRACEBACK:")
    logger.error(f"  - Full traceback: {traceback.format_exc()}")

    error_details = {
        "tool": tool_name,
        "error_type": type(error).__name__,
        "message": str(error),
        "timestamp": asyncio.get_event_loop().time(),
    }

    logger.error(f"BASE ERROR DETAILS:")
    logger.error(f"  - error_details: {error_details}")

    # Add additional details for LightRAG errors
    if isinstance(error, LightRAGError):
        logger.error("LIGHTRAG ERROR DETECTED:")
        logger.error(f"  - LightRAG error type: {type(error)}")
        try:
            error_dict = error.to_dict()
            logger.error(f"  - error.to_dict(): {error_dict}")
            error_details.update(error_dict)
        except Exception as e:
            logger.error(f"  - error.to_dict() failed: {e}")

        # Log different error types at appropriate levels with structured context
        error_context = {
            "tool": tool_name,
            "error_type": type(error).__name__,
            "status_code": getattr(error, "status_code", None),
            "response_data": getattr(error, "response_data", {}),
        }

        logger.error(f"ERROR CONTEXT: {error_context}")

        if isinstance(error, (LightRAGConnectionError, LightRAGTimeoutError)):
            logger.warning(
                f"Connection/timeout error in {tool_name}: {error}", extra=error_context
            )
        elif isinstance(error, LightRAGAuthError):
            logger.error(
                f"Authentication error in {tool_name}: {error}", extra=error_context
            )
        elif isinstance(error, LightRAGValidationError):
            logger.warning(
                f"Validation error in {tool_name}: {error}", extra=error_context
            )
        elif isinstance(error, LightRAGServerError):
            logger.error(f"Server error in {tool_name}: {error}", extra=error_context)
        else:
            logger.error(f"API error in {tool_name}: {error}", extra=error_context)
    else:
        logger.error("NON-LIGHTRAG ERROR:")
        # Handle Pydantic validation errors specifically
        if hasattr(error, "errors") and callable(getattr(error, "errors")):
            logger.error("  - Pydantic validation error detected")
            try:
                validation_errors = error.errors()
                logger.error(f"  - validation_errors: {validation_errors}")
                error_details["validation_errors"] = validation_errors
                logger.warning(
                    f"Input validation error in {tool_name}: {validation_errors}"
                )
            except Exception as e:
                logger.error(f"  - error.errors() failed: {e}")
                logger.error(f"Unexpected error in {tool_name}: {error}")
        else:
            logger.error(f"  - Generic error: {error}")
            logger.error(f"Unexpected error in {tool_name}: {error}")

    logger.error(f"FINAL ERROR DETAILS:")
    logger.error(f"  - error_details: {error_details}")

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(error_details, indent=2))],
        isError=True,
    )


@server.list_tools()
async def handle_list_tools() -> List[Tool]:  # ListToolsResult:
    """List available tools."""
    logger.info("=" * 80)
    logger.info("LISTING AVAILABLE MCP TOOLS")
    logger.info("=" * 80)
    logger.info("LIST_TOOLS HANDLER STARTED:")
    logger.info(f"  - Function: handle_list_tools")
    logger.info(f"  - Server: {server}")
    logger.info(f"  - Server type: {type(server)}")

    # Create tools list with explicit validation
    tools: List[Tool] = []
    logger.info("TOOLS LIST INITIALIZATION:")
    logger.info(f"  - Initial tools list: {tools}")
    logger.info(f"  - Tools list type: {type(tools)}")
    logger.info("  - Starting tool creation process...")

    # Document Management Tools
    tools.extend(
        [
            Tool(
                name="upload_document",
                description=(
                    "Create one document. Use exactly one form: file_path; file_url; "
                    "or filename + text_content. For inline text, filename is the "
                    "first argument."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Document name; required with text_content.",
                        },
                        "text_content": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Raw UTF-8 document content.",
                        },
                        "file_path": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Path on the MCP server filesystem.",
                        },
                        "file_url": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Public http(s) URL containing a filename.",
                        },
                    },
                    "oneOf": [
                        {"required": ["file_path"]},
                        {"required": ["file_url"]},
                        {"required": ["filename", "text_content"]},
                    ],
                    "required": [],
                },
            ),
            Tool(
                name="scan_documents",
                description="Scan for new documents in LightRAG",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_documents",
                description="Retrieve all documents from LightRAG",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_documents_paginated",
                description="Retrieve documents with pagination. IMPORTANT: page_size must be 10-100 (server enforces minimum for performance). Use page_size=20 for typical browsing.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "page": {
                            "type": "integer",
                            "description": "Page number (1-based)",
                            "minimum": 1,
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of documents per page",
                            "minimum": 1,
                            "maximum": 100,
                        },
                    },
                    "required": ["page", "page_size"],
                },
            ),
            Tool(
                name="delete_document",
                description="Delete a specific document by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "ID of the document to delete",
                        }
                    },
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="update_document",
                description=(
                    "Completely replace an existing document. Use exactly one form: "
                    "file_path; file_url; or filename + text_content. The MCP derives "
                    "the name for path/URL sources, deletes that existing document, "
                    "waits for deletion, and uploads the complete new version."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "minLength": 1},
                        "text_content": {"type": "string", "minLength": 1},
                        "file_path": {"type": "string", "minLength": 1},
                        "file_url": {"type": "string", "minLength": 1},
                        "delete_timeout": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 600,
                            "default": 60,
                        },
                    },
                    "oneOf": [
                        {"required": ["file_path"]},
                        {"required": ["file_url"]},
                        {"required": ["filename", "text_content"]},
                    ],
                    "required": [],
                },
            ),
            Tool(
                name="append_text",
                description=(
                    "Append text to the end of an existing MCP-managed text document "
                    "identified by filename. The MCP reconstructs the complete text, "
                    "deletes the old LightRAG document, and indexes the new full version. "
                    "For documents created outside this MCP, call update_document once "
                    "with the complete content first."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "minLength": 1},
                        "text_content": {"type": "string", "minLength": 1},
                        "separator": {"type": "string", "default": "\n"},
                        "delete_timeout": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 600,
                            "default": 60,
                        },
                    },
                    "required": ["filename", "text_content"],
                },
            ),
            # Tool(
            #     name="clear_documents",
            #     description="Clear all documents from LightRAG",
            #     inputSchema={
            #         "type": "object",
            #         "properties": {},
            #         "required": []
            #     }
            # ),
        ]
    )

    # Query Tools (2 tools)
    tools.extend(
        [
            Tool(
                name="query_text",
                description="Query LightRAG with text",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Query text"},
                        "mode": {
                            "type": "string",
                            "description": "Query mode",
                            "enum": ["naive", "local", "global", "hybrid", "mix"],
                            "default": "hybrid",
                        },
                        "only_need_context": {
                            "type": "boolean",
                            "description": "Whether to only return context without generation",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            # query_text_stream is intentionally not advertised: MCP tool calls
            # return one final result, and this handler has to buffer all upstream
            # chunks. The compatibility handler remains bounded for older clients.
        ]
    )

    # Knowledge Graph Tools (7 tools)
    tools.extend(
        [
            Tool(
                name="get_knowledge_graph",
                description="Retrieve the knowledge graph from LightRAG",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_graph_labels",
                description="Get labels from the knowledge graph",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="check_entity_exists",
                description="Check if an entity exists in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_name": {
                            "type": "string",
                            "description": "Name of the entity to check",
                        }
                    },
                    "required": ["entity_name"],
                },
            ),
            Tool(
                name="update_entity",
                description="Update an entity in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "ID of the entity to update",
                        },
                        "properties": {
                            "type": "object",
                            "description": "Properties to update",
                        },
                    },
                    "required": ["entity_id", "properties"],
                },
            ),
            # Tool(
            #     name="update_relation",
            #     description="Update a relation in the knowledge graph",
            #     inputSchema={
            #         "type": "object",
            #         "properties": {
            #             "relation_id": {
            #                 "type": "string",
            #                 "description": "ID of the relation to update"
            #             },
            #             "properties": {
            #                 "type": "object",
            #                 "description": "Properties to update"
            #             }
            #         },
            #         "required": ["relation_id", "properties"]
            #     }
            # ),
            Tool(
                name="update_relation",
                description="Update a relation in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source_id": {
                            "type": "string",
                            "description": "ID of the source entity",
                        },
                        "target_id": {
                            "type": "string",
                            "description": "ID of the target entity",
                        },
                        "updated_data": {
                            "type": "object",
                            "description": "Properties to update on the relation",
                        },
                    },
                    "required": ["source_id", "target_id", "updated_data"],
                },
            ),
            Tool(
                name="delete_entity",
                description="Delete an entity from the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "ID of the entity to delete",
                        }
                    },
                    "required": ["entity_id"],
                },
            ),
            Tool(
                name="delete_relation",
                description="Delete a relation from the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "relation_id": {
                            "type": "string",
                            "description": "ID of the relation to delete",
                        },
                    },
                    "required": ["relation_id"],
                },
            ),
        ]
    )

    # System Management Tools (5 tools)
    tools.extend(
        [
            Tool(
                name="get_pipeline_status",
                description="Get the pipeline status from LightRAG",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_track_status",
                description="Get track status by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "track_id": {
                            "type": "string",
                            "description": "ID of the track to get status for",
                        }
                    },
                    "required": ["track_id"],
                },
            ),
            Tool(
                name="get_document_status_counts",
                description="Get document status counts",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            # Tool(
            #     name="clear_cache",
            #     description="Clear LightRAG cache",
            #     inputSchema={
            #         "type": "object",
            #         "properties": {},
            #         "required": []
            #     }
            # ),
            Tool(
                name="get_health",
                description="Check LightRAG server health",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
        ]
    )

    # Workspace Admin Tools (4 tools) — gateway mode only, admin-key required
    admin_tools = [
        Tool(
            name="create_workspace",
            description=(
                "Create a new workspace and generate its initial API key. "
                "The slug must start with a letter and contain only lowercase "
                "letters, digits, '_' or '-' (max 63 chars). Returns workspace "
                "metadata and the initial api key (shown_once=true). Only "
                "available in gateway mode with an admin key."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 63,
                        "pattern": "^[a-z][a-z0-9_-]{0,62}$",
                        "description": "Workspace identifier (lowercase, starts with letter)",
                    },
                    "display_name": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Human-readable name (optional, defaults to slug)",
                    },
                },
                "required": ["slug"],
            },
        ),
        Tool(
            name="issue_key",
            description=(
                "Issue a new workspace API key. The workspace must exist. "
                "Returns the new key with shown_once=true. Use this to provision "
                "additional keys or after a compromise. Gateway mode, admin key "
                "only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Workspace slug to issue a key for",
                    }
                },
                "required": ["workspace"],
            },
        ),
        Tool(
            name="revoke_key",
            description=(
                "Revoke a workspace API key by its prefix (first 18 chars, e.g. "
                "'lr_main_ABC123'). Revoked keys can no longer authenticate. "
                "Returns the number of keys revoked (0 or 1). Gateway mode, admin "
                "key only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Key prefix to revoke (first 18 characters)",
                    }
                },
                "required": ["prefix"],
            },
        ),
        Tool(
            name="rotate_key",
            description=(
                "Rotate a workspace key: issue a new key for the workspace. "
                "(Full revoke+issue is not implemented yet; old keys remain valid "
                "until manually revoked via revoke_key.) Returns the new api key "
                "with shown_once=true. Gateway mode, admin key only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Workspace slug to rotate a key for",
                    }
                },
                "required": ["workspace"],
            },
        ),
    ]

    # Dynamic admin-tools visibility: only expose admin tools in gateway mode
    # when the env key (or per-call override) has admin privileges. Simple
    # mode = no admin tools (the gateway endpoints don't exist).
    gateway_url = os.getenv("LIGHTRAG_GATEWAY_URL")
    admin_key = os.getenv("LIGHTRAG_API_KEY")
    show_admin = False

    if gateway_url and admin_key:
        # Probe gateway's /_workspaces endpoint with X-Admin-Key. A 200
        # response means the key is an admin key; 401 means unauthorized.
        # Cache the result globally so we only check once per process.
        global _is_admin_cache
        if _is_admin_cache is None:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=5.0) as http:
                    response = await http.get(
                        f"{gateway_url.rstrip('/')}/_workspaces",
                        headers={"X-Admin-Key": admin_key},
                    )
                    # 200 = admin, 401 = not admin, other = treat as not admin
                    show_admin = response.status_code == 200
                    _is_admin_cache = show_admin
                    logger.info(
                        "Gateway admin check: %s (status %d)",
                        "admin" if show_admin else "not admin",
                        response.status_code,
                    )
            except Exception as exc:
                # Network/timeout errors = assume not admin, don't block startup
                logger.warning("Gateway admin check failed: %s", exc)
                _is_admin_cache = False
        else:
            show_admin = _is_admin_cache

    if show_admin:
        tools.extend(admin_tools)
        logger.info("Admin tools exposed: current key is gateway admin")
    else:
        if gateway_url:
            logger.info(
                "Admin tools hidden: gateway mode but key is not admin (or check failed)"
            )
        else:
            logger.info("Admin tools hidden: not in gateway mode")

    logger.info("TOOLS CREATION COMPLETED:")
    logger.info(f"  - Total tools created: {len(tools)}")
    logger.info(f"  - Tools list type: {type(tools)}")
    logger.info(f"  - Tools list length: {len(tools)}")

    # Log tool categories
    doc_tools = [
        t
        for t in tools
        if any(
            keyword in t.name
            for keyword in [
                "insert",
                "upload",
                "scan",
                "get_documents",
                "delete_document",
                "clear_documents",
            ]
        )
    ]
    query_tools = [t for t in tools if "query" in t.name]
    kg_tools = [
        t
        for t in tools
        if any(
            keyword in t.name
            for keyword in ["knowledge", "graph", "entity", "relation", "labels"]
        )
    ]
    system_tools = [
        t
        for t in tools
        if any(
            keyword in t.name
            for keyword in ["pipeline", "track", "status", "health", "cache"]
        )
    ]

    logger.info("TOOLS BY CATEGORY:")
    logger.info(f"  - Document Management Tools: {len(doc_tools)}")
    for tool in doc_tools:
        logger.info(f"    - {tool.name}")
    logger.info(f"  - Query Tools: {len(query_tools)}")
    for tool in query_tools:
        logger.info(f"    - {tool.name}")
    logger.info(f"  - Knowledge Graph Tools: {len(kg_tools)}")
    for tool in kg_tools:
        logger.info(f"    - {tool.name}")
    logger.info(f"  - System Management Tools: {len(system_tools)}")
    for tool in system_tools:
        logger.info(f"    - {tool.name}")

    # Comprehensive validation
    logger.info("TOOLS VALIDATION:")
    validation_errors = []
    for i, tool in enumerate(tools):
        logger.info(f"  - Validating tool {i}: {tool.name}")

        if not isinstance(tool, Tool):
            error_msg = f"Tool {i} is not a Tool instance: {type(tool)}"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        # Validate tool properties
        if not hasattr(tool, "name") or not tool.name:
            error_msg = f"Tool {i} has no name or empty name"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        if not hasattr(tool, "description") or not tool.description:
            error_msg = (
                f"Tool {i} ({tool.name}) has no description or empty description"
            )
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        if not hasattr(tool, "inputSchema") or not tool.inputSchema:
            error_msg = (
                f"Tool {i} ({tool.name}) has no inputSchema or empty inputSchema"
            )
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        # Validate input schema structure
        schema = tool.inputSchema
        if not isinstance(schema, dict):
            error_msg = (
                f"Tool {i} ({tool.name}) inputSchema is not a dict: {type(schema)}"
            )
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        if "type" not in schema or schema["type"] != "object":
            error_msg = f"Tool {i} ({tool.name}) inputSchema missing 'type': 'object'"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        if "properties" not in schema:
            error_msg = f"Tool {i} ({tool.name}) inputSchema missing 'properties'"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        if "required" not in schema:
            error_msg = f"Tool {i} ({tool.name}) inputSchema missing 'required'"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue

        logger.info(f"    - Tool {i} ({tool.name}): VALIDATION PASSED")
        logger.info(f"      - Name: '{tool.name}'")
        logger.info(f"      - Description length: {len(tool.description)}")
        logger.info(f"      - Properties count: {len(schema.get('properties', {}))}")
        logger.info(f"      - Required fields: {schema.get('required', [])}")

    # Check for validation errors
    if validation_errors:
        logger.error("TOOLS VALIDATION FAILED:")
        for error in validation_errors:
            logger.error(f"  - {error}")
        raise ValueError(
            f"Tool validation failed with {len(validation_errors)} errors: {validation_errors}"
        )

    logger.info("TOOLS VALIDATION COMPLETED:")
    logger.info(f"  - All {len(tools)} tools passed validation")

    # Create result exactly like working server
    logger.info("CREATING LIST_TOOLS_RESULT:")
    try:
        result = ListToolsResult(tools=tools)
        logger.info(f"  - ListToolsResult created successfully")
        logger.info(f"  - Result type: {type(result)}")
        logger.info(f"  - Result.tools type: {type(result.tools)}")
        logger.info(f"  - Result.tools length: {len(result.tools)}")

        # Validate result
        if not hasattr(result, "tools"):
            raise ValueError("ListToolsResult missing 'tools' attribute")

        if not isinstance(result.tools, list):
            raise ValueError(
                f"ListToolsResult.tools is not a list: {type(result.tools)}"
            )

        if len(result.tools) != len(tools):
            raise ValueError(
                f"ListToolsResult.tools length mismatch: {len(result.tools)} != {len(tools)}"
            )

        logger.info("  - ListToolsResult validation passed")

    except Exception as e:
        logger.error("LIST_TOOLS_RESULT CREATION FAILED:")
        logger.error(f"  - Exception type: {type(e)}")
        logger.error(f"  - Exception message: {str(e)}")
        logger.error(f"  - Exception args: {e.args}")
        logger.error(f"  - Tools count: {len(tools)}")
        import traceback

        logger.error(f"  - Full traceback: {traceback.format_exc()}")
        raise

    logger.info("LIST_TOOLS HANDLER COMPLETED:")
    logger.info(f"  - Returning {len(tools)} tools")
    logger.info(f"  - Return type: {type(tools)}")
    logger.info("=" * 80)

    return tools


def _get_lightrag_client() -> LightRAGClient:
    """Create the shared API client lazily from non-secret configuration.

    Mode selection: if ``LIGHTRAG_GATEWAY_URL`` is set, all traffic goes to the
    workspace gateway (which validates the key and routes to a workspace); the
    operator's env ``LIGHTRAG_API_KEY`` is then the superadmin key. Otherwise
    the client talks to LightRAG directly with that same key (simple/legacy
    mode, one workspace). The shared connection pool is identical in both
    modes; per-call workspace routing is handled by a request-scoped key
    override (see :func:`set_request_api_key`), not by swapping clients.
    """
    global lightrag_client
    if lightrag_client is None:
        gateway_url = os.getenv("LIGHTRAG_GATEWAY_URL")
        base_url = gateway_url or os.getenv("LIGHTRAG_BASE_URL", "http://localhost:9621")
        lightrag_client = LightRAGClient(
            base_url=base_url,
            api_key=os.getenv("LIGHTRAG_API_KEY"),
            timeout=float(os.getenv("LIGHTRAG_TIMEOUT", "30.0")),
        )
        if gateway_url:
            logger.info("Gateway mode: routing through %s", gateway_url)
        else:
            logger.info("Simple mode: talking to LightRAG directly at %s", base_url)
    return lightrag_client


@server.call_tool()
async def handle_call_tool_refactored(
    tool_name: str, arguments: Dict[str, Any]
) -> CallToolResult:
    """Validate and dispatch one MCP call through the typed handler registry."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return _create_error_response(
            LightRAGValidationError(f"Unknown tool: {tool_name}"), tool_name
        )

    # ``api_key`` is a routing meta-parameter, not a tool argument: it lets a
    # caller target a specific workspace in gateway mode by passing that
    # workspace's key. Strip it before validation (the typed argument models
    # use extra="forbid") and bind it to the current async task so the shared
    # client carries it as a per-request X-API-Key header.
    call_arguments = dict(arguments or {})
    per_call_key = call_arguments.pop("api_key", None)
    token = set_request_api_key(per_call_key)
    try:
        result = await handler(call_arguments, _get_lightrag_client())
        logger.info("Tool %s completed successfully", tool_name)
        return _create_success_response(result, tool_name)
    except Exception as error:
        logger.error("Tool %s failed: %s", tool_name, type(error).__name__)
        return _create_error_response(error, tool_name)
    finally:
        reset_request_api_key(token)


async def main() -> None:
    """Main entry point for the MCP server."""
    logger.info("=" * 100)
    logger.info("STARTING LIGHTRAG MCP SERVER")
    logger.info("=" * 100)

    # Log system information
    import sys
    import platform

    logger.info("SYSTEM INFORMATION:")
    logger.info(f"  - Python version: {sys.version}")
    logger.info(f"  - Platform: {platform.platform()}")
    logger.info(f"  - Current working directory: {os.getcwd()}")
    logger.info(f"  - Script path: {__file__}")

    logger.info(
        "Configuration: LIGHTRAG_BASE_URL set=%s, LIGHTRAG_API_KEY set=%s, "
        "LIGHTRAG_FILE_PATH_ROOT set=%s",
        bool(os.getenv("LIGHTRAG_BASE_URL")),
        bool(os.getenv("LIGHTRAG_API_KEY")),
        bool(os.getenv("LIGHTRAG_FILE_PATH_ROOT")),
    )

    try:
        logger.info("SERVER INITIALIZATION:")
        logger.info("  - Validating server configuration...")
        logger.info(f"  - Server name: lightrag-mcp-connect")
        logger.info(f"  - Server object: {server}")
        logger.info(f"  - Server type: {type(server)}")

        logger.info("STDIO SERVER SETUP:")
        async with stdio_server() as (read_stream, write_stream):
            logger.info("  - STDIO server context entered successfully")
            logger.info(f"  - Read stream: {read_stream}")
            logger.info(f"  - Write stream: {write_stream}")
            logger.info("  - MCP server initialized, starting communication loop")

            # Initialize server capabilities
            logger.info("CAPABILITIES INITIALIZATION:")
            capabilities = server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            )
            logger.info(f"  - Server capabilities: {capabilities}")
            logger.info(f"  - Capabilities type: {type(capabilities)}")

            # Create initialization options
            init_options = InitializationOptions(
                server_name="lightrag-mcp-connect",
                server_version="1.1.0",
                capabilities=capabilities,
            )
            logger.info(f"INITIALIZATION OPTIONS:")
            logger.info(f"  - Init options: {init_options}")
            logger.info(f"  - Init options type: {type(init_options)}")

            logger.info("STARTING SERVER RUN LOOP:")
            await server.run(
                read_stream,
                write_stream,
                init_options,
            )

    except KeyboardInterrupt:
        logger.info("SERVER SHUTDOWN:")
        logger.info("  - Server shutdown requested by user (KeyboardInterrupt)")
    except ConnectionError as e:
        logger.error("CONNECTION ERROR:")
        logger.error(f"  - Connection error during server startup: {e}")
        logger.error(f"  - Error type: {type(e)}")
        logger.error(f"  - Error args: {e.args}")
        import traceback

        logger.error(f"  - Traceback: {traceback.format_exc()}")
        raise
    except Exception as e:
        logger.error("FATAL SERVER ERROR:")
        logger.error(f"  - Fatal server error: {e}")
        logger.error(f"  - Error type: {type(e)}")
        logger.error(f"  - Error args: {e.args}")
        import traceback

        logger.error(f"  - Traceback: {traceback.format_exc()}")
        raise
    finally:
        logger.info("SERVER CLEANUP:")
        logger.info("  - LightRAG MCP server shutting down")
        global lightrag_client
        if lightrag_client:
            logger.info("  - Closing LightRAG client...")
            try:
                await lightrag_client.__aexit__(None, None, None)
                logger.info("  - LightRAG client closed successfully")
            except Exception as e:
                logger.warning(f"  - Error closing LightRAG client: {e}")
                logger.warning(f"  - Error type: {type(e)}")
        else:
            logger.info("  - No LightRAG client to close")
        logger.info("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())

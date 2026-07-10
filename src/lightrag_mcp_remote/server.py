"""
MCP server for LightRAG integration.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from pydantic import AnyUrl

from .client import (
    LightRAGClient, 
    LightRAGError, 
    LightRAGConnectionError, 
    LightRAGAuthError, 
    LightRAGValidationError, 
    LightRAGAPIError,
    LightRAGTimeoutError,
    LightRAGServerError
)

# Configure logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# Set specific log levels for different components
logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce httpx noise
logging.getLogger("mcp").setLevel(logging.INFO)

# Initialize the MCP server
server = Server("lightrag-mcp-remote")

# Global client instance
lightrag_client: Optional[LightRAGClient] = None


def _validate_tool_arguments(tool_name: str, arguments: Dict[str, Any]) -> None:
    """Validate tool arguments against expected schemas."""
    # Define required arguments for each tool
    required_args = {
        "insert_text": ["text"],
        "insert_texts": ["texts"],
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
        file_url = arguments.get("file_url")
        file_content = arguments.get("file_content")
        file_path = arguments.get("file_path")
        if not file_url and not file_content and not file_path:
            raise LightRAGValidationError(
                "upload_document requires one of: file_url, file_path, or file_content (base64) + filename"
            )
        if file_content and not arguments.get("filename"):
            raise LightRAGValidationError("filename is required when using file_content")

    elif tool_name == "get_documents_paginated":
        page = arguments.get("page", 1)
        page_size = arguments.get("page_size", 10)
        
        if not isinstance(page, int) or page < 1:
            raise LightRAGValidationError("Page must be a positive integer")
        if not isinstance(page_size, int) or page_size < 1 or page_size > 100:
            raise LightRAGValidationError("Page size must be an integer between 1 and 100")
    
    elif tool_name == "query_text" or tool_name == "query_text_stream":
        mode = arguments.get("mode", "hybrid")
        valid_modes = ["naive", "local", "global", "hybrid"]
        if mode not in valid_modes:
            raise LightRAGValidationError(f"Invalid query mode '{mode}'. Must be one of: {valid_modes}")
    
    logger.debug(f"Tool arguments validation passed for {tool_name}")


def _serialize_result(result: Any) -> str:
    """Serialize result to JSON, handling Pydantic models."""
    if hasattr(result, 'dict'):
        # Pydantic model
        return json.dumps(result.model_dump(), indent=2)
    elif hasattr(result, '__dict__'):
        # Regular object with __dict__
        return json.dumps(result.__dict__, indent=2)
    else:
        # Fallback to direct serialization
        return json.dumps(result, indent=2)


def _create_success_response(result: Any, tool_name: str) -> dict:
    """Create standardized MCP success response."""
    logger.info("=" * 60)
    logger.info("CREATING SUCCESS RESPONSE")
    logger.info("=" * 60)
    logger.info(f"SUCCESS RESPONSE INPUT:")
    logger.info(f"  - tool_name: '{tool_name}'")
    logger.info(f"  - result type: {type(result)}")
    logger.info(f"  - result content: {repr(result)}")
    
    # Handle Pydantic models properly
    logger.info("RESPONSE SERIALIZATION:")
    if hasattr(result, 'model_dump'):
        logger.info("  - Using result.model_dump() (Pydantic v2)")
        try:
            serialized_data = result.model_dump()
            logger.info(f"  - model_dump() result: {serialized_data}")
            response_text = json.dumps(serialized_data, indent=2)
            logger.info(f"  - JSON serialization successful")
        except Exception as e:
            logger.error(f"  - model_dump() failed: {e}")
            response_text = str(result)
    elif hasattr(result, 'dict'):
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
    logger.info(f"  - Content preview: {response_text[:200]}{'...' if len(response_text) > 200 else ''}")
    
    # Create response dictionary
    response_dict = {
        "content": [
            {
                "type": "text",
                "text": response_text
            }
        ]
    }
    
    logger.info(f"SUCCESS RESPONSE CREATED:")
    logger.info(f"  - Response type: {type(response_dict)}")
    logger.info(f"  - Response keys: {list(response_dict.keys())}")
    logger.info(f"  - Content length: {len(response_dict['content'])}")
    logger.info(f"  - Content[0] type: {response_dict['content'][0]['type']}")
    logger.info(f"  - Content[0] text length: {len(response_dict['content'][0]['text'])}")
    logger.info("=" * 60)
    
    return response_dict


def _create_error_response(error: Exception, tool_name: str) -> dict:
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
        "timestamp": asyncio.get_event_loop().time()
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
            "status_code": getattr(error, 'status_code', None),
            "response_data": getattr(error, 'response_data', {})
        }
        
        logger.error(f"ERROR CONTEXT: {error_context}")
        
        if isinstance(error, (LightRAGConnectionError, LightRAGTimeoutError)):
            logger.warning(f"Connection/timeout error in {tool_name}: {error}", extra=error_context)
        elif isinstance(error, LightRAGAuthError):
            logger.error(f"Authentication error in {tool_name}: {error}", extra=error_context)
        elif isinstance(error, LightRAGValidationError):
            logger.warning(f"Validation error in {tool_name}: {error}", extra=error_context)
        elif isinstance(error, LightRAGServerError):
            logger.error(f"Server error in {tool_name}: {error}", extra=error_context)
        else:
            logger.error(f"API error in {tool_name}: {error}", extra=error_context)
    else:
        logger.error("NON-LIGHTRAG ERROR:")
        # Handle Pydantic validation errors specifically
        if hasattr(error, 'errors') and callable(getattr(error, 'errors')):
            logger.error("  - Pydantic validation error detected")
            try:
                validation_errors = error.errors()
                logger.error(f"  - validation_errors: {validation_errors}")
                error_details["validation_errors"] = validation_errors
                logger.warning(f"Input validation error in {tool_name}: {validation_errors}")
            except Exception as e:
                logger.error(f"  - error.errors() failed: {e}")
                logger.error(f"Unexpected error in {tool_name}: {error}")
        else:
            logger.error(f"  - Generic error: {error}")
            logger.error(f"Unexpected error in {tool_name}: {error}")
    
    logger.error(f"FINAL ERROR DETAILS:")
    logger.error(f"  - error_details: {error_details}")
    
    # Create error response dictionary
    error_response = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(error_details, indent=2)
            }
        ],
        "isError": True
    }
    
    logger.error(f"ERROR RESPONSE CREATED:")
    logger.error(f"  - Response type: {type(error_response)}")
    logger.error(f"  - Response keys: {list(error_response.keys())}")
    logger.error(f"  - isError: {error_response['isError']}")
    logger.error(f"  - Content length: {len(error_response['content'])}")
    logger.error("=" * 60)
    
    return error_response


@server.list_tools()
async def handle_list_tools() -> List[Tool]:#ListToolsResult:
    """List available tools."""
    logger.info("=" * 80)
    logger.info("LISTING AVAILABLE MCP TOOLS")
    logger.info("=" * 80)
    logger.info("LIST_TOOLS HANDLER STARTED:")
    logger.info(f"  - Function: handle_list_tools")
    logger.info(f"  - Server: {server}")
    logger.info(f"  - Server type: {type(server)}")
    
    # Create tools list with explicit validation
    tools = []
    logger.info("TOOLS LIST INITIALIZATION:")
    logger.info(f"  - Initial tools list: {tools}")
    logger.info(f"  - Tools list type: {type(tools)}")
    logger.info("  - Starting tool creation process...")
    
    # Document Management Tools (8 tools)
    tools.extend([
        Tool(
            name="insert_text",
            description="Insert text content into LightRAG",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text content to insert"
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="insert_texts",
            description="Insert multiple text documents into LightRAG",
            inputSchema={
                "type": "object",
                "properties": {
                    "texts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "metadata": {"type": "object"}
                            },
                            "required": ["content"]
                        },
                        "description": "Array of text documents to insert"
                    }
                },
                "required": ["texts"]
            }
        ),
        Tool(
            name="upload_document",
            description=(
                "Upload a document to LightRAG. Three ways to provide the "
                "file — pick based on where this MCP server actually runs "
                "and what you have access to, not by default habit:\n"
                "1. file_url — a public http(s) URL (e.g. an uploaded "
                "attachment or artifact link). The MCP SERVER fetches it "
                "itself. Best option when you have one: nothing about the "
                "file passes through your context or output tokens, and it "
                "works no matter where the server runs.\n"
                "2. file_path — a path on the MCP SERVER's own filesystem. "
                "Use ONLY when you've confirmed the server runs on the same "
                "machine you do (local/same-host deployments). Free like "
                "file_url, but fails with 'File does not exist' otherwise.\n"
                "3. file_content (base64) + filename — last resort, for "
                "remote/hosted servers when you have no URL for the file. "
                "Produce the base64 with a deterministic tool/script call "
                "(e.g. a shell `base64` command, or equivalent code "
                "execution) that returns the encoded string directly into "
                "the tool argument — do NOT compute or transcribe the "
                "base64 yourself token by token as part of your own "
                "reasoning. Besides wasting output tokens on anything but a "
                "trivially small file, a large inline base64 blob can also "
                "trip content-safety classifiers that flag it as "
                "obfuscated data — prefer file_url or file_path whenever "
                "either is available."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_url": {
                        "type": "string",
                        "description": "Public http(s) URL to fetch the file from — the MCP server downloads it directly. Best option when available. Optionally pair with filename to override the name derived from the URL."
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file on the MCP SERVER's own filesystem. Free like file_url, but only works when the server runs on the same machine as you — otherwise fails with 'File does not exist'."
                    },
                    "file_content": {
                        "type": "string",
                        "description": "Last resort. The file's bytes, base64-encoded — produced by a script/tool call, not typed out manually. Use together with filename."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename to store it as, e.g. 'report.pdf'. Required with file_content; optional override for file_url."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="scan_documents",
            description="Scan for new documents in LightRAG",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_documents",
            description="Retrieve all documents from LightRAG",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
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
                        "minimum": 1
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Number of documents per page",
                        "minimum": 1,
                        "maximum": 100
                    }
                },
                "required": ["page", "page_size"]
            }
        ),
        Tool(
            name="delete_document",
            description="Delete a specific document by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "ID of the document to delete"
                    }
                },
                "required": ["document_id"]
            }
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
    ])
    
    # Query Tools (2 tools)
    tools.extend([
        Tool(
            name="query_text",
            description="Query LightRAG with text",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query text"
                    },
                    "mode": {
                        "type": "string",
                        "description": "Query mode",
                        "enum": ["naive", "local", "global", "hybrid"],
                        "default": "hybrid"
                    },
                    "only_need_context": {
                        "type": "boolean",
                        "description": "Whether to only return context without generation",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="query_text_stream",
            description="Stream query results from LightRAG",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query text"
                    },
                    "mode": {
                        "type": "string",
                        "description": "Query mode",
                        "enum": ["naive", "local", "global", "hybrid"],
                        "default": "hybrid"
                    },
                    "only_need_context": {
                        "type": "boolean",
                        "description": "Whether to only return context without generation",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        ),
    ])
    
    # Knowledge Graph Tools (7 tools)
    tools.extend([
        Tool(
            name="get_knowledge_graph",
            description="Retrieve the knowledge graph from LightRAG",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_graph_labels",
            description="Get labels from the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="check_entity_exists",
            description="Check if an entity exists in the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to check"
                    }
                },
                "required": ["entity_name"]
            }
        ),
        Tool(
            name="update_entity",
            description="Update an entity in the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "ID of the entity to update"
                    },
                    "properties": {
                        "type": "object",
                        "description": "Properties to update"
                    }
                },
                "required": ["entity_id", "properties"]
            }
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
                        "description": "ID of the source entity"
                    },
                    "target_id": {
                        "type": "string",
                        "description": "ID of the target entity"
                    },
                    "updated_data": {
                        "type": "object",
                        "description": "Properties to update on the relation"
                    }
                },
                "required": ["source_id", "target_id", "updated_data"]
            }
        ),
        Tool(
            name="delete_entity",
            description="Delete an entity from the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "ID of the entity to delete"
                    }
                },
                "required": ["entity_id"]
            }
        ),
        Tool(
            name="delete_relation",
            description="Delete a relation from the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "relation_id": {
                        "type": "string",
                        "description": "ID of the relation to delete"
                    }
                },
                "required": ["relation_id"]
            }
        ),
    ])
    
    # System Management Tools (5 tools)
    tools.extend([
        Tool(
            name="get_pipeline_status",
            description="Get the pipeline status from LightRAG",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_track_status",
            description="Get track status by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "track_id": {
                        "type": "string",
                        "description": "ID of the track to get status for"
                    }
                },
                "required": ["track_id"]
            }
        ),
        Tool(
            name="get_document_status_counts",
            description="Get document status counts",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
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
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ])
    
    logger.info("TOOLS CREATION COMPLETED:")
    logger.info(f"  - Total tools created: {len(tools)}")
    logger.info(f"  - Tools list type: {type(tools)}")
    logger.info(f"  - Tools list length: {len(tools)}")
    
    # Log tool categories
    doc_tools = [t for t in tools if any(keyword in t.name for keyword in ['insert', 'upload', 'scan', 'get_documents', 'delete_document', 'clear_documents'])]
    query_tools = [t for t in tools if 'query' in t.name]
    kg_tools = [t for t in tools if any(keyword in t.name for keyword in ['knowledge', 'graph', 'entity', 'relation', 'labels'])]
    system_tools = [t for t in tools if any(keyword in t.name for keyword in ['pipeline', 'track', 'status', 'health', 'cache'])]
    
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
        if not hasattr(tool, 'name') or not tool.name:
            error_msg = f"Tool {i} has no name or empty name"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue
        
        if not hasattr(tool, 'description') or not tool.description:
            error_msg = f"Tool {i} ({tool.name}) has no description or empty description"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue
        
        if not hasattr(tool, 'inputSchema') or not tool.inputSchema:
            error_msg = f"Tool {i} ({tool.name}) has no inputSchema or empty inputSchema"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue
        
        # Validate input schema structure
        schema = tool.inputSchema
        if not isinstance(schema, dict):
            error_msg = f"Tool {i} ({tool.name}) inputSchema is not a dict: {type(schema)}"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue
        
        if 'type' not in schema or schema['type'] != 'object':
            error_msg = f"Tool {i} ({tool.name}) inputSchema missing 'type': 'object'"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue
        
        if 'properties' not in schema:
            error_msg = f"Tool {i} ({tool.name}) inputSchema missing 'properties'"
            logger.error(f"    - VALIDATION ERROR: {error_msg}")
            validation_errors.append(error_msg)
            continue
        
        if 'required' not in schema:
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
        raise ValueError(f"Tool validation failed with {len(validation_errors)} errors: {validation_errors}")
    
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
        if not hasattr(result, 'tools'):
            raise ValueError("ListToolsResult missing 'tools' attribute")
        
        if not isinstance(result.tools, list):
            raise ValueError(f"ListToolsResult.tools is not a list: {type(result.tools)}")
        
        if len(result.tools) != len(tools):
            raise ValueError(f"ListToolsResult.tools length mismatch: {len(result.tools)} != {len(tools)}")
        
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

@server.call_tool()
async def handle_call_tool(self, request: CallToolRequest) -> dict:
    """Handle tool calls."""
    global lightrag_client
    
    # === COMPREHENSIVE LOGGING START ===
    logger.info("=" * 80)
    logger.info("MCP TOOL CALL HANDLER STARTED")
    logger.info("=" * 80)
    
    # Log all incoming parameters with full details
    logger.info(f"HANDLER INPUT ANALYSIS:")
    logger.info(f"  - self type: {type(self)}")
    logger.info(f"  - self content: {repr(self)}")
    logger.info(f"  - self length: {len(str(self)) if isinstance(self, str) else 'N/A'}")
    logger.info(f"  - request type: {type(request)}")
    logger.info(f"  - request content: {repr(request)}")
    
    # Check all attributes of self and request
    if hasattr(self, '__dict__'):
        logger.info(f"  - self.__dict__: {self.__dict__}")
    else:
        logger.info(f"  - self has no __dict__ attribute")
        
    if hasattr(request, '__dict__'):
        logger.info(f"  - request.__dict__: {request.__dict__}")
    else:
        logger.info(f"  - request has no __dict__ attribute")
        
    # Log request attributes if it's a dict
    if isinstance(request, dict):
        logger.info(f"  - request keys: {list(request.keys())}")
        logger.info(f"  - request values: {list(request.values())}")
        for key, value in request.items():
            logger.info(f"    - request['{key}'] = {repr(value)} (type: {type(value)})")
    
    # The MCP library passes tool_name as 'self' and empty dict as 'request'
    tool_name = self  # self is the tool name string
    arguments = request or {}   # arguments are always empty for now
    
    logger.info(f"EXTRACTED PARAMETERS:")
    logger.info(f"  - tool_name: '{tool_name}' (type: {type(tool_name)})")
    logger.info(f"  - arguments: {arguments} (type: {type(arguments)})")
    logger.info(f"  - arguments length: {len(arguments)}")
    
    # Log global client state
    logger.info(f"GLOBAL CLIENT STATE:")
    logger.info(f"  - lightrag_client is None: {lightrag_client is None}")
    if lightrag_client is not None:
        logger.info(f"  - lightrag_client type: {type(lightrag_client)}")
        logger.info(f"  - lightrag_client base_url: {getattr(lightrag_client, 'base_url', 'N/A')}")
    
    logger.info("=" * 80)



    
    logger.info(f"TOOL EXECUTION PHASE:")
    logger.info(f"  - Processing tool: '{tool_name}'")
    logger.info(f"  - Tool arguments: {json.dumps(arguments, indent=2)}")
    
    # Client initialization with detailed logging
    if lightrag_client is None:
        logger.info("CLIENT INITIALIZATION:")
        logger.info("  - LightRAG client is None, initializing new client")
        try:
            logger.info("  - Creating LightRAGClient instance...")
            
            # Get configuration from environment variables
            base_url = os.getenv("LIGHTRAG_BASE_URL", "http://localhost:9621")
            api_key = os.getenv("LIGHTRAG_API_KEY", None)
            timeout = float(os.getenv("LIGHTRAG_TIMEOUT", "30.0"))
            
            logger.info("CLIENT CONFIGURATION:")
            logger.info(f"  - base_url: {base_url}")
            logger.info(f"  - api_key: {'***REDACTED***' if api_key else 'None'}")
            logger.info(f"  - timeout: {timeout}")
            
            lightrag_client = LightRAGClient(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout
            )
            logger.info(f"  - Client initialized successfully: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Client timeout: {lightrag_client.timeout}")
            logger.info(f"  - Client has API key: {lightrag_client.api_key is not None}")
        except Exception as e:
            logger.error(f"CLIENT INITIALIZATION FAILED:")
            logger.error(f"  - Exception type: {type(e)}")
            logger.error(f"  - Exception message: {str(e)}")
            logger.error(f"  - Exception args: {e.args}")
            import traceback
            logger.error(f"  - Full traceback: {traceback.format_exc()}")
            return _create_error_response(
                LightRAGConnectionError(f"Failed to initialize LightRAG client: {str(e)}"),
                tool_name
            )
    else:
        logger.info("CLIENT STATE:")
        logger.info(f"  - Using existing LightRAG client: {type(lightrag_client)}")
        logger.info(f"  - Client base_url: {lightrag_client.base_url}")
    
    try:
        logger.info("ARGUMENT VALIDATION:")
        logger.info(f"  - Validating arguments for tool: {tool_name}")
        logger.info(f"  - Arguments to validate: {arguments}")
        
        # Validate that required arguments are present for each tool
        _validate_tool_arguments(tool_name, arguments)
        logger.info("  - Argument validation passed")
        
        logger.info("TOOL DISPATCH:")
        logger.info(f"  - Dispatching to tool handler for: {tool_name}")
        
        # Document Management Tools (8 tools)
        if tool_name == "insert_text":
            logger.info("EXECUTING INSERT_TEXT TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            text = arguments.get("text", "")
            logger.info(f"INSERT_TEXT PARAMETERS:")
            logger.info(f"  - text: '{text[:100]}{'...' if len(text) > 100 else ''}' (length: {len(text)})")
            logger.info(f"  - text type: {type(text)}")
            
            if not text or not text.strip():
                logger.error("INSERT_TEXT VALIDATION ERROR:")
                logger.error("  - Text is empty or whitespace only")
                raise LightRAGValidationError("Text cannot be empty")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.insert_text()...")
            
            try:
                result = await lightrag_client.insert_text(text)
                logger.info("INSERT_TEXT SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Track ID: {result_dump.get('track_id', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("INSERT_TEXT FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Text length: {len(text)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "insert_texts":
            logger.info("EXECUTING INSERT_TEXTS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            texts = arguments.get("texts", [])
            logger.info(f"INSERT_TEXTS PARAMETERS:")
            logger.info(f"  - texts count: {len(texts)}")
            logger.info(f"  - texts type: {type(texts)}")
            
            if not texts or not isinstance(texts, list):
                logger.error("INSERT_TEXTS VALIDATION ERROR:")
                logger.error("  - Texts is empty or not a list")
                raise LightRAGValidationError("Texts must be a non-empty list")
            
            for i, text_doc in enumerate(texts):
                logger.info(f"  - Text {i}: {text_doc}")
                if not isinstance(text_doc, dict) or 'content' not in text_doc:
                    logger.error(f"INSERT_TEXTS VALIDATION ERROR:")
                    logger.error(f"  - Text {i} missing required 'content' field")
                    raise LightRAGValidationError(f"Text {i} must have 'content' field")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.insert_texts()...")
            
            try:
                result = await lightrag_client.insert_texts(texts)
                logger.info("INSERT_TEXTS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Track ID: {result_dump.get('track_id', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("INSERT_TEXTS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Texts count: {len(texts)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "upload_document":
            logger.info("EXECUTING UPLOAD_DOCUMENT TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments keys: {list(arguments.keys())}")

            file_url = arguments.get("file_url")
            file_content_b64 = arguments.get("file_content")
            filename = arguments.get("filename")
            file_path = arguments.get("file_path", "")

            try:
                if file_url:
                    logger.info(f"  - Using file_url: '{file_url}', filename override: '{filename}'")
                    result = await lightrag_client.upload_document_from_url(file_url, filename)
                elif file_content_b64:
                    logger.info(f"  - Using file_content (base64), filename: '{filename}'")
                    import base64
                    try:
                        content_bytes = base64.b64decode(file_content_b64, validate=True)
                    except Exception as e:
                        raise LightRAGValidationError(f"Invalid base64 file_content: {e}")
                    logger.info(f"  - Decoded content: {len(content_bytes)} bytes")
                    result = await lightrag_client.upload_document_content(content_bytes, filename)
                else:
                    logger.info(f"  - Using file_path: '{file_path}'")
                    if not file_path or not file_path.strip():
                        raise LightRAGValidationError("File path cannot be empty")
                    if not os.path.exists(file_path):
                        raise LightRAGValidationError(
                            f"File does not exist on the MCP server's own filesystem: {file_path}. "
                            "This path was resolved on the machine running the MCP server, not on "
                            "your (the calling agent's) machine — those are almost never the same "
                            "for a remote/hosted MCP connection. Re-try this upload using file_url "
                            "(if you have a public link to the file) or file_content (base64-encoded "
                            "bytes) + filename instead of file_path."
                        )
                    file_size = os.path.getsize(file_path)
                    logger.info(f"  - File size: {file_size} bytes, readable: {os.access(file_path, os.R_OK)}")
                    result = await lightrag_client.upload_document(file_path)

                logger.info("UPLOAD_DOCUMENT SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Track ID: {result_dump.get('track_id', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")

                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("UPLOAD_DOCUMENT FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "scan_documents":
            logger.info("EXECUTING SCAN_DOCUMENTS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.scan_documents()...")
            
            try:
                result = await lightrag_client.scan_documents()
                logger.info("SCAN_DOCUMENTS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Track ID: {result_dump.get('track_id', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                        new_docs = result_dump.get('new_documents', [])
                        logger.info(f"  - New documents found: {len(new_docs)}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("SCAN_DOCUMENTS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "get_documents":
            logger.info("EXECUTING GET_DOCUMENTS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.get_documents()...")
            
            try:
                result = await lightrag_client.get_documents()
                logger.info("GET_DOCUMENTS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        statuses = result_dump.get('statuses', {})
                        logger.info(f"DOCUMENT STATUSES:")
                        for status, docs in statuses.items():
                            logger.info(f"    - {status}: {len(docs) if docs else 0} documents")
                            if docs and len(docs) > 0:
                                logger.info(f"    - First {status} doc ID: {docs[0].get('id', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("GET_DOCUMENTS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "get_documents_paginated":
            logger.info("EXECUTING GET_DOCUMENTS_PAGINATED TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            page = arguments.get("page", 1)
            page_size = arguments.get("page_size", 10)
            logger.info(f"GET_DOCUMENTS_PAGINATED PARAMETERS:")
            logger.info(f"  - page: {page} (type: {type(page)})")
            logger.info(f"  - page_size: {page_size} (type: {type(page_size)})")
            
            if not isinstance(page, int) or page < 1:
                logger.error("GET_DOCUMENTS_PAGINATED VALIDATION ERROR:")
                logger.error(f"  - Invalid page: {page}")
                raise LightRAGValidationError("Page must be a positive integer")
            
            if not isinstance(page_size, int) or page_size < 1 or page_size > 100:
                logger.error("GET_DOCUMENTS_PAGINATED VALIDATION ERROR:")
                logger.error(f"  - Invalid page_size: {page_size}")
                raise LightRAGValidationError("Page size must be an integer between 1 and 100")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.get_documents_paginated()...")
            
            try:
                result = await lightrag_client.get_documents_paginated(page, page_size)
                logger.info("GET_DOCUMENTS_PAGINATED SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        documents = result_dump.get('documents', [])
                        pagination = result_dump.get('pagination', {})
                        status_counts = result_dump.get('status_counts', {})
                        logger.info(f"PAGINATION DETAILS:")
                        logger.info(f"    - Documents returned: {len(documents)}")
                        logger.info(f"    - Current page: {pagination.get('page', 'N/A')}")
                        logger.info(f"    - Page size: {pagination.get('page_size', 'N/A')}")
                        logger.info(f"    - Total count: {pagination.get('total_count', 'N/A')}")
                        logger.info(f"    - Total pages: {pagination.get('total_pages', 'N/A')}")
                        logger.info(f"    - Has next: {pagination.get('has_next', 'N/A')}")
                        logger.info(f"    - Has prev: {pagination.get('has_prev', 'N/A')}")
                        logger.info(f"STATUS COUNTS:")
                        for status, count in status_counts.items():
                            logger.info(f"    - {status}: {count}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("GET_DOCUMENTS_PAGINATED FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Page: {page}")
                logger.error(f"  - Page size: {page_size}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "delete_document":
            logger.info("EXECUTING DELETE_DOCUMENT TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            document_id = arguments.get("document_id", "")
            logger.info(f"DELETE_DOCUMENT PARAMETERS:")
            logger.info(f"  - document_id: '{document_id}'")
            logger.info(f"  - document_id type: {type(document_id)}")
            
            if not document_id or not document_id.strip():
                logger.error("DELETE_DOCUMENT VALIDATION ERROR:")
                logger.error("  - Document ID is empty or whitespace only")
                raise LightRAGValidationError("Document ID cannot be empty")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.delete_document()...")
            logger.warning(f"  - DESTRUCTIVE OPERATION: Deleting document {document_id}")
            
            try:
                result = await lightrag_client.delete_document(document_id)
                logger.info("DELETE_DOCUMENT SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                logger.warning(f"  - Document {document_id} has been deleted")
                return response
            except Exception as e:
                logger.error("DELETE_DOCUMENT FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Document ID: {document_id}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "clear_documents":
            logger.info("EXECUTING CLEAR_DOCUMENTS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.clear_documents()...")
            logger.warning("  - DESTRUCTIVE OPERATION: Clearing ALL documents")
            
            try:
                result = await lightrag_client.clear_documents()
                logger.info("CLEAR_DOCUMENTS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                logger.warning("  - ALL documents have been cleared")
                return response
            except Exception as e:
                logger.error("CLEAR_DOCUMENTS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        # Query Tools (2 tools)
        elif tool_name == "query_text":
            logger.info("EXECUTING QUERY_TEXT TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            # Extract and validate parameters
            query = arguments.get("query", "")
            mode = arguments.get("mode", "hybrid")
            only_need_context = arguments.get("only_need_context", False)
            
            logger.info(f"QUERY_TEXT PARAMETERS:")
            logger.info(f"  - query: '{query}' (length: {len(query)})")
            logger.info(f"  - mode: '{mode}'")
            logger.info(f"  - only_need_context: {only_need_context}")
            logger.info(f"  - query type: {type(query)}")
            
            # Validate query
            if not query or not query.strip():
                logger.error("QUERY_TEXT VALIDATION ERROR:")
                logger.error("  - Query is empty or whitespace only")
                raise LightRAGValidationError("Query cannot be empty")
            
            valid_modes = ["naive", "local", "global", "hybrid"]
            if mode not in valid_modes:
                logger.error("QUERY_TEXT MODE ERROR:")
                logger.error(f"  - Invalid mode: '{mode}'")
                logger.error(f"  - Valid modes: {valid_modes}")
                raise LightRAGValidationError(f"Invalid query mode '{mode}'. Must be one of: {valid_modes}")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.query_text()...")
            
            try:
                result = await lightrag_client.query_text(
                    query, mode=mode, only_need_context=only_need_context
                )
                logger.info("QUERY_TEXT SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, '__dict__'):
                    logger.info(f"  - Result.__dict__: {result.__dict__}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Response length: {len(str(result_dump.get('response', '')))}")
                        logger.info(f"  - Results count: {len(result_dump.get('results', []))}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                logger.info("  - Calling _create_success_response()...")
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response type: {type(response)}")
                logger.info(f"  - Success response keys: {list(response.keys())}")
                return response
            except Exception as e:
                logger.error("QUERY_TEXT FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Exception args: {e.args}")
                logger.error(f"  - Query: '{query}'")
                logger.error(f"  - Mode: '{mode}'")
                logger.error(f"  - Only need context: {only_need_context}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "query_text_stream":
            logger.info("EXECUTING QUERY_TEXT_STREAM TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            # Extract and validate parameters
            query = arguments.get("query", "")
            mode = arguments.get("mode", "hybrid")
            only_need_context = arguments.get("only_need_context", False)
            
            logger.info(f"QUERY_TEXT_STREAM PARAMETERS:")
            logger.info(f"  - query: '{query}' (length: {len(query)})")
            logger.info(f"  - mode: '{mode}'")
            logger.info(f"  - only_need_context: {only_need_context}")
            logger.info(f"  - query type: {type(query)}")
            
            # Validate query
            if not query or not query.strip():
                logger.error("QUERY_TEXT_STREAM VALIDATION ERROR:")
                logger.error("  - Query is empty or whitespace only")
                raise LightRAGValidationError("Query cannot be empty")
            
            valid_modes = ["naive", "local", "global", "hybrid"]
            if mode not in valid_modes:
                logger.error("QUERY_TEXT_STREAM MODE ERROR:")
                logger.error(f"  - Invalid mode: '{mode}'")
                logger.error(f"  - Valid modes: {valid_modes}")
                raise LightRAGValidationError(f"Invalid query mode '{mode}'. Must be one of: {valid_modes}")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Starting streaming query...")
            
            try:
                # Collect streaming results
                chunks = []
                chunk_count = 0
                total_length = 0
                
                logger.info("STREAMING COLLECTION:")
                async for chunk in lightrag_client.query_text_stream(
                    query, mode=mode, only_need_context=only_need_context
                ):
                    chunks.append(chunk)
                    chunk_count += 1
                    chunk_length = len(str(chunk))
                    total_length += chunk_length
                    
                    # Log every 50th chunk to avoid spam
                    if chunk_count % 50 == 0:
                        logger.info(f"  - Collected {chunk_count} chunks, total length: {total_length}")
                
                logger.info("QUERY_TEXT_STREAM SUCCESS:")
                logger.info(f"  - Total chunks collected: {chunk_count}")
                logger.info(f"  - Total response length: {total_length}")
                logger.info(f"  - Average chunk size: {total_length / chunk_count if chunk_count > 0 else 0:.2f}")
                
                # Join chunks into final response
                streaming_response = "".join(chunks)
                result = {"streaming_response": streaming_response}
                
                logger.info(f"STREAMING RESULT:")
                logger.info(f"  - Final response length: {len(streaming_response)}")
                logger.info(f"  - Response preview: {streaming_response[:200]}{'...' if len(streaming_response) > 200 else ''}")
                
                # Create MCP response
                response = CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2))]
                )
                logger.info(f"  - MCP response created successfully")
                return response
                
            except Exception as e:
                logger.error("QUERY_TEXT_STREAM FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Exception args: {e.args}")
                logger.error(f"  - Query: '{query}'")
                logger.error(f"  - Mode: '{mode}'")
                logger.error(f"  - Only need context: {only_need_context}")
                logger.error(f"  - Chunks collected before error: {chunk_count}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        # Knowledge Graph Tools (7 tools)
        elif tool_name == "get_knowledge_graph":
            logger.info("EXECUTING GET_KNOWLEDGE_GRAPH TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.get_knowledge_graph()...")
            
            try:
                result = await lightrag_client.get_knowledge_graph()
                logger.info("GET_KNOWLEDGE_GRAPH SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        nodes = result_dump.get('nodes', [])
                        edges = result_dump.get('edges', [])
                        logger.info(f"KNOWLEDGE GRAPH STATISTICS:")
                        logger.info(f"    - Total nodes (entities): {len(nodes)}")
                        logger.info(f"    - Total edges (relationships): {len(edges)}")
                        logger.info(f"    - Is truncated: {result_dump.get('is_truncated', 'N/A')}")
                        
                        # Log entity types
                        if nodes:
                            entity_types = {}
                            for node in nodes[:10]:  # Sample first 10
                                entity_type = node.get('properties', {}).get('entity_type', 'unknown')
                                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
                            logger.info(f"    - Sample entity types: {entity_types}")
                            logger.info(f"    - First entity: {nodes[0].get('id', 'N/A')}")
                        
                        # Log relationship types
                        if edges:
                            rel_types = {}
                            for edge in edges[:10]:  # Sample first 10
                                rel_type = edge.get('type', 'unknown')
                                rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
                            logger.info(f"    - Sample relationship types: {rel_types}")
                            logger.info(f"    - First relationship: {edges[0].get('id', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("GET_KNOWLEDGE_GRAPH FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "get_graph_labels":
            logger.info("EXECUTING GET_GRAPH_LABELS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.get_graph_labels()...")
            
            try:
                result = await lightrag_client.get_graph_labels()
                logger.info("GET_GRAPH_LABELS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        entity_labels = result_dump.get('entity_labels', [])
                        relation_labels = result_dump.get('relation_labels', [])
                        logger.info(f"GRAPH LABELS:")
                        logger.info(f"    - Entity labels count: {len(entity_labels)}")
                        logger.info(f"    - Relation labels count: {len(relation_labels)}")
                        if entity_labels:
                            logger.info(f"    - Entity labels: {entity_labels}")
                        if relation_labels:
                            logger.info(f"    - Relation labels: {relation_labels}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("GET_GRAPH_LABELS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "check_entity_exists":
            logger.info("EXECUTING CHECK_ENTITY_EXISTS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            entity_name = arguments.get("entity_name", "")
            logger.info(f"CHECK_ENTITY_EXISTS PARAMETERS:")
            logger.info(f"  - entity_name: '{entity_name}'")
            logger.info(f"  - entity_name type: {type(entity_name)}")
            
            if not entity_name or not entity_name.strip():
                logger.error("CHECK_ENTITY_EXISTS VALIDATION ERROR:")
                logger.error("  - Entity name is empty or whitespace only")
                raise LightRAGValidationError("Entity name cannot be empty")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.check_entity_exists()...")
            
            try:
                result = await lightrag_client.check_entity_exists(entity_name)
                logger.info("CHECK_ENTITY_EXISTS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        exists = result_dump.get('exists', False)
                        logger.info(f"ENTITY EXISTENCE CHECK:")
                        logger.info(f"    - Entity '{entity_name}' exists: {exists}")
                        logger.info(f"    - Entity ID: {result_dump.get('entity_id', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("CHECK_ENTITY_EXISTS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Entity name: {entity_name}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "update_entity":
            logger.info("EXECUTING UPDATE_ENTITY TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            entity_id = arguments.get("entity_id", "")
            properties = arguments.get("properties", {})
            logger.info(f"UPDATE_ENTITY PARAMETERS:")
            logger.info(f"  - entity_id: '{entity_id}'")
            logger.info(f"  - entity_id type: {type(entity_id)}")
            logger.info(f"  - properties: {properties}")
            logger.info(f"  - properties type: {type(properties)}")
            logger.info(f"  - properties keys: {list(properties.keys()) if isinstance(properties, dict) else 'N/A'}")
            
            if not entity_id or not entity_id.strip():
                logger.error("UPDATE_ENTITY VALIDATION ERROR:")
                logger.error("  - Entity ID is empty or whitespace only")
                raise LightRAGValidationError("Entity ID cannot be empty")
            
            if not isinstance(properties, dict):
                logger.error("UPDATE_ENTITY VALIDATION ERROR:")
                logger.error(f"  - Properties must be a dictionary, got {type(properties)}")
                raise LightRAGValidationError("Properties must be a dictionary")
            
            if not properties:
                logger.warning("UPDATE_ENTITY WARNING:")
                logger.warning("  - Properties dictionary is empty, no updates will be made")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.update_entity()...")
            
            try:
                result = await lightrag_client.update_entity(entity_id, properties)
                logger.info("UPDATE_ENTITY SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"ENTITY UPDATE DETAILS:")
                        logger.info(f"    - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"    - Message: {result_dump.get('message', 'N/A')}")
                        data = result_dump.get('data', {})
                        if data:
                            logger.info(f"    - Updated entity name: {data.get('entity_name', 'N/A')}")
                            graph_data = data.get('graph_data', {})
                            if graph_data:
                                logger.info(f"    - Entity type: {graph_data.get('entity_type', 'N/A')}")
                                logger.info(f"    - Updated properties: {list(graph_data.keys())}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("UPDATE_ENTITY FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Entity ID: {entity_id}")
                logger.error(f"  - Properties: {properties}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        # elif tool_name == "update_relation":
        #     logger.info("EXECUTING UPDATE_RELATION TOOL:")
        #     logger.info(f"  - Tool: {tool_name}")
        #     logger.info(f"  - Client type: {type(lightrag_client)}")
        #     logger.info(f"  - Client base_url: {lightrag_client.base_url}")
        #     logger.info(f"  - Raw arguments: {arguments}")
            
        #     relation_id = arguments.get("relation_id", "")
        #     properties = arguments.get("properties", {})
        #     logger.info(f"UPDATE_RELATION PARAMETERS:")
        #     logger.info(f"  - relation_id: '{relation_id}'")
        #     logger.info(f"  - relation_id type: {type(relation_id)}")
        #     logger.info(f"  - properties: {properties}")
        #     logger.info(f"  - properties type: {type(properties)}")
        #     logger.info(f"  - properties keys: {list(properties.keys()) if isinstance(properties, dict) else 'N/A'}")
            
        #     if not relation_id or not relation_id.strip():
        #         logger.error("UPDATE_RELATION VALIDATION ERROR:")
        #         logger.error("  - Relation ID is empty or whitespace only")
        #         raise LightRAGValidationError("Relation ID cannot be empty")
            
        #     if not isinstance(properties, dict):
        #         logger.error("UPDATE_RELATION VALIDATION ERROR:")
        #         logger.error(f"  - Properties must be a dictionary, got {type(properties)}")
        #         raise LightRAGValidationError("Properties must be a dictionary")
            
        #     if not properties:
        #         logger.warning("UPDATE_RELATION WARNING:")
        #         logger.warning("  - Properties dictionary is empty, no updates will be made")
            
        #     logger.info("  - Parameter validation passed")
        #     logger.info("  - Calling lightrag_client.update_relation()...")
            
        #     try:
        #         result = await lightrag_client.update_relation(relation_id, properties)
        #         logger.info("UPDATE_RELATION SUCCESS:")
        #         logger.info(f"  - Result type: {type(result)}")
        #         logger.info(f"  - Result content: {repr(result)}")
        #         if hasattr(result, 'model_dump'):
        #             try:
        #                 result_dump = result.model_dump()
        #                 logger.info(f"  - Result.model_dump(): {result_dump}")
        #                 logger.info(f"RELATION UPDATE DETAILS:")
        #                 logger.info(f"    - Status: {result_dump.get('status', 'N/A')}")
        #                 logger.info(f"    - Message: {result_dump.get('message', 'N/A')}")
        #                 data = result_dump.get('data', {})
        #                 if data:
        #                     logger.info(f"    - Updated relation ID: {data.get('relation_id', 'N/A')}")
        #                     logger.info(f"    - Source: {data.get('source', 'N/A')}")
        #                     logger.info(f"    - Target: {data.get('target', 'N/A')}")
        #             except Exception as e:
        #                 logger.error(f"  - model_dump() failed: {e}")
                
        #         response = _create_success_response(result, tool_name)
        #         logger.info(f"  - Success response created")
        #         return response
        #     except Exception as e:
        #         logger.error("UPDATE_RELATION FAILED:")
        #         logger.error(f"  - Exception type: {type(e)}")
        #         logger.error(f"  - Exception message: {str(e)}")
        #         logger.error(f"  - Relation ID: {relation_id}")
        #         logger.error(f"  - Properties: {properties}")
        #         import traceback
        #         logger.error(f"  - Full traceback: {traceback.format_exc()}")
        #         raise

        elif tool_name == "update_relation":
            logger.info("EXECUTING UPDATE_RELATION TOOL:")
            logger.info(f"  - Raw arguments: {arguments}")

            source_id = arguments.get("source_id", "")
            target_id = arguments.get("target_id", "")
            updated_data = arguments.get("updated_data", {})

            logger.info(f"UPDATE_RELATION PARAMETERS:")
            logger.info(f"  - source_id: '{source_id}'")
            logger.info(f"  - target_id: '{target_id}'")
            logger.info(f"  - updated_data: {updated_data}")

            if not source_id.strip():
                logger.error("UPDATE_RELATION VALIDATION ERROR: source_id is empty")
                raise LightRAGValidationError("source_id cannot be empty")

            if not target_id.strip():
                logger.error("UPDATE_RELATION VALIDATION ERROR: target_id is empty")
                raise LightRAGValidationError("target_id cannot be empty")

            if not isinstance(updated_data, dict):
                logger.error("UPDATE_RELATION VALIDATION ERROR: updated_data must be a dict")
                raise LightRAGValidationError("updated_data must be a dictionary")

            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.update_relation()...")

            try:
                result = await lightrag_client.update_relation(source_id, target_id, updated_data)
                logger.info("UPDATE_RELATION SUCCESS:")
                logger.info(f"  - Result content: {repr(result)}")
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error(f"UPDATE_RELATION FAILED: {e}")
                raise

        elif tool_name == "delete_entity":
            logger.info("EXECUTING DELETE_ENTITY TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            entity_id = arguments.get("entity_id", "")
            logger.info(f"DELETE_ENTITY PARAMETERS:")
            logger.info(f"  - entity_id: '{entity_id}'")
            logger.info(f"  - entity_id type: {type(entity_id)}")
            
            if not entity_id or not entity_id.strip():
                logger.error("DELETE_ENTITY VALIDATION ERROR:")
                logger.error("  - Entity ID is empty or whitespace only")
                raise LightRAGValidationError("Entity ID cannot be empty")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.delete_entity()...")
            logger.warning(f"  - DESTRUCTIVE OPERATION: Deleting entity {entity_id}")
            
            try:
                result = await lightrag_client.delete_entity(entity_id)
                logger.info("DELETE_ENTITY SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                logger.warning(f"  - Entity {entity_id} has been deleted")
                return response
            except Exception as e:
                logger.error("DELETE_ENTITY FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Entity ID: {entity_id}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "delete_relation":
            logger.info("EXECUTING DELETE_RELATION TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            relation_id = arguments.get("relation_id", "")
            logger.info(f"DELETE_RELATION PARAMETERS:")
            logger.info(f"  - relation_id: '{relation_id}'")
            logger.info(f"  - relation_id type: {type(relation_id)}")
            
            if not relation_id or not relation_id.strip():
                logger.error("DELETE_RELATION VALIDATION ERROR:")
                logger.error("  - Relation ID is empty or whitespace only")
                raise LightRAGValidationError("Relation ID cannot be empty")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.delete_relation()...")
            logger.warning(f"  - DESTRUCTIVE OPERATION: Deleting relation {relation_id}")
            
            try:
                result = await lightrag_client.delete_relation(relation_id)
                logger.info("DELETE_RELATION SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"  - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"  - Message: {result_dump.get('message', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                logger.warning(f"  - Relation {relation_id} has been deleted")
                return response
            except Exception as e:
                logger.error("DELETE_RELATION FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Relation ID: {relation_id}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        # System Management Tools (5 tools)
        elif tool_name == "get_pipeline_status":
            logger.info("EXECUTING GET_PIPELINE_STATUS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info(f"  - Arguments length: {len(arguments)}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.get_pipeline_status()...")
            
            try:
                result = await lightrag_client.get_pipeline_status()
                logger.info("GET_PIPELINE_STATUS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, '__dict__'):
                    logger.info(f"  - Result.__dict__: {result.__dict__}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"PIPELINE STATUS DETAILS:")
                        logger.info(f"    - autoscanned: {result_dump.get('autoscanned', 'N/A')}")
                        logger.info(f"    - busy: {result_dump.get('busy', 'N/A')}")
                        logger.info(f"    - job_name: {result_dump.get('job_name', 'N/A')}")
                        logger.info(f"    - job_start: {result_dump.get('job_start', 'N/A')}")
                        logger.info(f"    - docs: {result_dump.get('docs', 'N/A')}")
                        logger.info(f"    - batchs: {result_dump.get('batchs', 'N/A')}")
                        logger.info(f"    - cur_batch: {result_dump.get('cur_batch', 'N/A')}")
                        logger.info(f"    - request_pending: {result_dump.get('request_pending', 'N/A')}")
                        logger.info(f"    - progress: {result_dump.get('progress', 'N/A')}")
                        logger.info(f"    - current_task: {result_dump.get('current_task', 'N/A')}")
                        logger.info(f"    - latest_message: {result_dump.get('latest_message', 'N/A')}")
                        history_messages = result_dump.get('history_messages', [])
                        logger.info(f"    - history_messages count: {len(history_messages) if history_messages else 0}")
                        if history_messages:
                            logger.info(f"    - latest history message: {history_messages[-1] if history_messages else 'N/A'}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                logger.info("  - Calling _create_success_response()...")
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response type: {type(response)}")
                logger.info(f"  - Success response keys: {list(response.keys())}")
                return response
            except Exception as e:
                logger.error("GET_PIPELINE_STATUS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Exception args: {e.args}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "get_track_status":
            logger.info("EXECUTING GET_TRACK_STATUS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Raw arguments: {arguments}")
            
            track_id = arguments.get("track_id", "")
            logger.info(f"GET_TRACK_STATUS PARAMETERS:")
            logger.info(f"  - track_id: '{track_id}'")
            logger.info(f"  - track_id type: {type(track_id)}")
            
            if not track_id or not track_id.strip():
                logger.error("GET_TRACK_STATUS VALIDATION ERROR:")
                logger.error("  - Track ID is empty or whitespace only")
                raise LightRAGValidationError("Track ID cannot be empty")
            
            logger.info("  - Parameter validation passed")
            logger.info("  - Calling lightrag_client.get_track_status()...")
            
            try:
                result = await lightrag_client.get_track_status(track_id)
                logger.info("GET_TRACK_STATUS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"TRACK STATUS DETAILS:")
                        logger.info(f"    - Track ID: {result_dump.get('track_id', 'N/A')}")
                        documents = result_dump.get('documents', [])
                        logger.info(f"    - Documents count: {len(documents)}")
                        logger.info(f"    - Total count: {result_dump.get('total_count', 'N/A')}")
                        status_summary = result_dump.get('status_summary', {})
                        logger.info(f"    - Status summary: {status_summary}")
                        if documents:
                            logger.info(f"    - First document ID: {documents[0].get('id', 'N/A')}")
                            logger.info(f"    - First document status: {documents[0].get('status', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("GET_TRACK_STATUS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Track ID: {track_id}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "get_document_status_counts":
            logger.info("EXECUTING GET_DOCUMENT_STATUS_COUNTS TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.get_document_status_counts()...")
            
            try:
                result = await lightrag_client.get_document_status_counts()
                logger.info("GET_DOCUMENT_STATUS_COUNTS SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        status_counts = result_dump.get('status_counts', {})
                        logger.info(f"DOCUMENT STATUS COUNTS:")
                        for status, count in status_counts.items():
                            logger.info(f"    - {status}: {count}")
                        total_docs = status_counts.get('all', 0)
                        processed_docs = status_counts.get('processed', 0)
                        failed_docs = status_counts.get('failed', 0)
                        pending_docs = status_counts.get('pending', 0)
                        processing_docs = status_counts.get('processing', 0)
                        logger.info(f"SUMMARY:")
                        logger.info(f"    - Total documents: {total_docs}")
                        logger.info(f"    - Success rate: {(processed_docs/total_docs*100) if total_docs > 0 else 0:.1f}%")
                        logger.info(f"    - Active processing: {processing_docs + pending_docs}")
                        if failed_docs > 0:
                            logger.warning(f"    - Failed documents: {failed_docs}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                return response
            except Exception as e:
                logger.error("GET_DOCUMENT_STATUS_COUNTS FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "clear_cache":
            logger.info("EXECUTING CLEAR_CACHE TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info(f"  - Arguments: {arguments}")
            logger.info("  - This tool requires no parameters")
            logger.info("  - Calling lightrag_client.clear_cache()...")
            logger.warning("  - CACHE OPERATION: Clearing system cache")
            
            try:
                result = await lightrag_client.clear_cache()
                logger.info("CLEAR_CACHE SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, 'model_dump'):
                    try:
                        result_dump = result.model_dump()
                        logger.info(f"  - Result.model_dump(): {result_dump}")
                        logger.info(f"CACHE CLEAR DETAILS:")
                        logger.info(f"    - Status: {result_dump.get('status', 'N/A')}")
                        logger.info(f"    - Message: {result_dump.get('message', 'N/A')}")
                        logger.info(f"    - Cache cleared: {result_dump.get('cache_cleared', 'N/A')}")
                        logger.info(f"    - Items cleared: {result_dump.get('items_cleared', 'N/A')}")
                    except Exception as e:
                        logger.error(f"  - model_dump() failed: {e}")
                
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response created")
                logger.info("  - System cache has been cleared")
                return response
            except Exception as e:
                logger.error("CLEAR_CACHE FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        elif tool_name == "get_health":
            logger.info("EXECUTING GET_HEALTH TOOL:")
            logger.info(f"  - Tool: {tool_name}")
            logger.info(f"  - Client type: {type(lightrag_client)}")
            logger.info(f"  - Client base_url: {lightrag_client.base_url}")
            logger.info("  - Calling lightrag_client.get_health()...")
            
            try:
                result = await lightrag_client.get_health()
                logger.info("GET_HEALTH SUCCESS:")
                logger.info(f"  - Result type: {type(result)}")
                logger.info(f"  - Result content: {repr(result)}")
                if hasattr(result, '__dict__'):
                    logger.info(f"  - Result.__dict__: {result.__dict__}")
                if hasattr(result, 'model_dump'):
                    logger.info(f"  - Result.model_dump(): {result.model_dump()}")
                logger.info("  - Calling _create_success_response()...")
                response = _create_success_response(result, tool_name)
                logger.info(f"  - Success response type: {type(response)}")
                logger.info(f"  - Success response: {response}")
                return response
            except Exception as e:
                logger.error("GET_HEALTH FAILED:")
                logger.error(f"  - Exception type: {type(e)}")
                logger.error(f"  - Exception message: {str(e)}")
                logger.error(f"  - Exception args: {e.args}")
                import traceback
                logger.error(f"  - Full traceback: {traceback.format_exc()}")
                raise
        
        else:
            error_msg = f"Unknown tool: {tool_name}"
            logger.error(error_msg)
            return CallToolResult(
                content=[TextContent(type="text", text=error_msg)],
                isError=True
            )
    
    except LightRAGError as e:
        logger.error("LIGHTRAG EXCEPTION CAUGHT:")
        logger.error(f"  - Exception type: {type(e)}")
        logger.error(f"  - Exception message: {str(e)}")
        logger.error(f"  - Tool name: {tool_name}")
        logger.error(f"  - Status code: {getattr(e, 'status_code', 'N/A')}")
        logger.error(f"  - Response data: {getattr(e, 'response_data', 'N/A')}")
        import traceback
        logger.error(f"  - Traceback: {traceback.format_exc()}")
        return _create_error_response(e, tool_name)
    
    except Exception as e:
        logger.error("GENERIC EXCEPTION CAUGHT:")
        logger.error(f"  - Exception type: {type(e)}")
        logger.error(f"  - Exception message: {str(e)}")
        logger.error(f"  - Exception args: {e.args}")
        logger.error(f"  - Tool name: {tool_name}")
        import traceback
        logger.error(f"  - Traceback: {traceback.format_exc()}")
        return _create_error_response(e, tool_name)


async def main():
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
    
    # Log environment variables
    logger.info("ENVIRONMENT VARIABLES:")
    for key, value in os.environ.items():
        if 'LIGHTRAG' in key.upper() or 'MCP' in key.upper():
            logger.info(f"  - {key}: {value}")
    
    try:
        logger.info("SERVER INITIALIZATION:")
        logger.info("  - Validating server configuration...")
        logger.info(f"  - Server name: lightrag-mcp-remote")
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
                server_name="lightrag-mcp-remote",
                server_version="0.1.0",
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

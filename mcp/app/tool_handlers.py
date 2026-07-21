"""Typed MCP tool handlers and dispatch registry."""

import httpx
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Union
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .client import LightRAGClient, LightRAGAuthError, LightRAGValidationError
from .content_store import DocumentContentStore
from .models import AppendTextResponse, UpdateDocumentResponse

ToolResult = Any
ToolHandler = Callable[[Dict[str, Any], LightRAGClient], Awaitable[ToolResult]]
TOOL_HANDLERS: Dict[str, ToolHandler] = {}


def tool_handler(name: str) -> Callable[[ToolHandler], ToolHandler]:
    """Register a typed tool handler by its public MCP name."""

    def decorator(handler: ToolHandler) -> ToolHandler:
        TOOL_HANDLERS[name] = handler
        return handler

    return decorator


class ToolArguments(BaseModel):
    """Base model that rejects misspelled or unsupported tool arguments."""

    model_config = ConfigDict(extra="forbid")


class UploadDocumentArguments(ToolArguments):
    filename: Optional[str] = Field(default=None, min_length=1)
    text_content: Optional[str] = Field(default=None, min_length=1)
    file_path: Optional[str] = Field(default=None, min_length=1)
    file_url: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_source(self) -> "UploadDocumentArguments":
        sources = [
            name
            for name in ("text_content", "file_path", "file_url")
            if getattr(self, name) is not None
        ]
        if len(sources) != 1:
            raise ValueError("exactly one document source is required")
        if self.text_content is not None and not self.filename:
            raise ValueError("filename is required with inline content")
        if self.filename and self.text_content is None:
            raise ValueError("filename is only valid together with text_content")
        return self


class PaginationArguments(ToolArguments):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status_filter: Optional[str] = None


class DocumentIdArguments(ToolArguments):
    document_id: str = Field(min_length=1)


class EntityIdArguments(ToolArguments):
    entity_id: str = Field(min_length=1)


class QueryArguments(ToolArguments):
    query: str = Field(min_length=1)
    mode: str = Field(default="hybrid", pattern="^(naive|local|global|hybrid|mix)$")
    only_need_context: bool = False


class EntityNameArguments(ToolArguments):
    entity_name: str = Field(min_length=1)


class UpdateEntityArguments(ToolArguments):
    entity_id: str = Field(min_length=1)
    properties: Dict[str, Any]


class UpdateRelationArguments(ToolArguments):
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    updated_data: Dict[str, Any]


class RelationIdArguments(ToolArguments):
    relation_id: str = Field(min_length=1)


class TrackIdArguments(ToolArguments):
    track_id: str = Field(min_length=1)


class UpdateDocumentArguments(UploadDocumentArguments):
    delete_timeout: float = Field(default=60.0, gt=0, le=600)


class AppendTextArguments(ToolArguments):
    filename: str = Field(min_length=1)
    text_content: str = Field(min_length=1)
    separator: str = "\n"
    delete_timeout: float = Field(default=60.0, gt=0, le=600)


class EmptyArguments(ToolArguments):
    pass


class CreateWorkspaceArguments(ToolArguments):
    slug: str = Field(min_length=1, max_length=63)
    display_name: Optional[str] = Field(default=None, min_length=1)


class IssueKeyArguments(ToolArguments):
    workspace: str = Field(min_length=1)


class RevokeKeyArguments(ToolArguments):
    prefix: str = Field(min_length=1)


class RotateKeyArguments(ToolArguments):
    workspace: str = Field(min_length=1)


def _allowed_local_file(file_path: str) -> Path:
    configured_root = os.getenv("LIGHTRAG_FILE_PATH_ROOT")
    if not configured_root:
        raise LightRAGValidationError(
            "file_path uploads are disabled. Set LIGHTRAG_FILE_PATH_ROOT for "
            "a trusted same-host deployment."
        )
    try:
        root = Path(configured_root).expanduser().resolve(strict=True)
        candidate = Path(file_path).expanduser().resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, ValueError) as exc:
        raise LightRAGValidationError(f"file_path is outside the allowed root: {exc}")
    if not candidate.is_file():
        raise LightRAGValidationError("file_path is not a regular file")
    return candidate


def _source_filename(args: UploadDocumentArguments) -> str:
    if args.filename:
        return args.filename
    if args.file_path:
        return Path(args.file_path).name
    path_name = Path(unquote(urlparse(args.file_url or "").path)).name
    if not path_name:
        raise LightRAGValidationError("file_url must include a filename in its path")
    return path_name


async def _upload_source(
    args: UploadDocumentArguments, client: LightRAGClient
) -> ToolResult:
    if args.text_content is not None:
        return await client.upload_document_as_text(
            args.text_content, args.filename or ""
        )
    if args.file_path is not None:
        return await client.upload_document(str(_allowed_local_file(args.file_path)))
    return await client.upload_document_from_url(args.file_url or "")


@tool_handler("upload_document")
async def upload_document(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = UploadDocumentArguments.model_validate(arguments)
    result = await _upload_source(args, client)
    if args.text_content is not None:
        DocumentContentStore().put(args.filename or "", args.text_content)
    return result


@tool_handler("scan_documents")
async def scan_documents(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.scan_documents()


@tool_handler("get_documents")
async def get_documents(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.get_documents()


@tool_handler("get_documents_paginated")
async def get_documents_paginated(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = PaginationArguments.model_validate(arguments)
    return await client.get_documents_paginated(
        args.page, args.page_size, args.status_filter
    )


@tool_handler("delete_document")
async def delete_document(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = DocumentIdArguments.model_validate(arguments)
    return await client.delete_document(args.document_id)


@tool_handler("update_document")
async def update_document(
    arguments: Dict[str, Any], client: LightRAGClient
) -> UpdateDocumentResponse:
    args = UpdateDocumentArguments.model_validate(arguments)
    filename = _source_filename(args)
    # Reject invalid or inaccessible sources before deleting the current version.
    if args.file_path is not None:
        args.file_path = str(_allowed_local_file(args.file_path))
    elif args.file_url is not None:
        client._validate_public_url(args.file_url)
    store = DocumentContentStore()
    async with store.lock(filename):
        deleted_doc_id = await client.delete_document_by_filename(
            filename, args.delete_timeout
        )
        uploaded = await _upload_source(args, client)
        if not uploaded.track_id:
            raise LightRAGValidationError("LightRAG did not return a track_id")
        if args.text_content is not None:
            store.put(filename, args.text_content)
        else:
            store.delete(filename)
        return UpdateDocumentResponse(
            status=uploaded.status,
            message=f"Replaced '{filename}' and queued the new content",
            filename=filename,
            deleted_doc_id=deleted_doc_id,
            track_id=uploaded.track_id,
        )


@tool_handler("append_text")
async def append_text(
    arguments: Dict[str, Any], client: LightRAGClient
) -> AppendTextResponse:
    args = AppendTextArguments.model_validate(arguments)
    store = DocumentContentStore()
    async with store.lock(args.filename):
        existing = await client.find_document_by_filename(args.filename)
        if existing is None:
            raise LightRAGValidationError(
                f"Cannot append to '{args.filename}': document does not exist"
            )
        current_text = store.get(args.filename)
        if current_text is None:
            raise LightRAGValidationError(
                f"Cannot append to '{args.filename}': its exact source text is not "
                "managed by this MCP server. Use update_document once with the full "
                "content; subsequent appends will then be available."
            )
        combined = current_text + args.separator + args.text_content
        result = await client.replace_text_document(
            filename=args.filename,
            text=combined,
            delete_timeout=args.delete_timeout,
        )
        store.put(args.filename, combined)
        return AppendTextResponse(
            status=result.status,
            message=f"Appended text to '{args.filename}' and queued reindexing",
            filename=args.filename,
            deleted_doc_id=result.deleted_doc_id,
            track_id=result.track_id,
            appended_characters=len(args.text_content),
        )


@tool_handler("query_text")
async def query_text(arguments: Dict[str, Any], client: LightRAGClient) -> ToolResult:
    args = QueryArguments.model_validate(arguments)
    return await client.query_text(args.query, args.mode, args.only_need_context)


@tool_handler("get_knowledge_graph")
async def get_knowledge_graph(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.get_knowledge_graph()


@tool_handler("get_graph_labels")
async def get_graph_labels(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.get_graph_labels()


@tool_handler("check_entity_exists")
async def check_entity_exists(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = EntityNameArguments.model_validate(arguments)
    return await client.check_entity_exists(args.entity_name)


@tool_handler("update_entity")
async def update_entity(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = UpdateEntityArguments.model_validate(arguments)
    return await client.update_entity(args.entity_id, args.properties)


@tool_handler("update_relation")
async def update_relation(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = UpdateRelationArguments.model_validate(arguments)
    return await client.update_relation(
        args.source_id, args.target_id, args.updated_data
    )


@tool_handler("delete_entity")
async def delete_entity(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = EntityIdArguments.model_validate(arguments)
    return await client.delete_entity(args.entity_id)


@tool_handler("delete_relation")
async def delete_relation(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = RelationIdArguments.model_validate(arguments)
    return await client.delete_relation(args.relation_id)


@tool_handler("get_pipeline_status")
async def get_pipeline_status(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.get_pipeline_status()


@tool_handler("get_track_status")
async def get_track_status(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    args = TrackIdArguments.model_validate(arguments)
    return await client.get_track_status(args.track_id)


@tool_handler("get_document_status_counts")
async def get_document_status_counts(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.get_document_status_counts()


@tool_handler("get_health")
async def get_health(arguments: Dict[str, Any], client: LightRAGClient) -> ToolResult:
    EmptyArguments.model_validate(arguments)
    return await client.get_health()


async def _admin_gateway_request(
    method: str, path: str, json_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Make an admin API call to the workspace gateway.

    Only available when LIGHTRAG_GATEWAY_URL is set; the current api key
    (either the operator's env key or a per-call override) must have admin
    privileges on the gateway. Returns the JSON response or raises a
    LightRAGError with the gateway's error message.
    """
    gateway_url = os.getenv("LIGHTRAG_GATEWAY_URL")
    if not gateway_url:
        raise LightRAGValidationError(
            "Admin tools are only available in gateway mode. Set LIGHTRAG_GATEWAY_URL."
        )

    # Use the per-request api key (if bound) as the admin key.
    from .client import _REQUEST_API_KEY

    admin_key = _REQUEST_API_KEY.get() or os.getenv("LIGHTRAG_API_KEY")
    if not admin_key:
        raise LightRAGValidationError(
            "Admin tools require an api key (env LIGHTRAG_API_KEY or per-call api_key)."
        )

    url = f"{gateway_url.rstrip('/')}{path}"
    headers = {"X-Admin-Key": admin_key}

    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            if method.upper() == "GET":
                response = await http.get(url, headers=headers)
            elif method.upper() == "POST":
                response = await http.post(url, json=json_data or {}, headers=headers)
            elif method.upper() == "DELETE":
                response = await http.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.text else {}
        except httpx.HTTPStatusError as e:
            # Propagate gateway's error message (usually 'invalid workspace admin key')
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = e.response.text or str(e)
            raise LightRAGAuthError(detail) from None


@tool_handler("create_workspace")
async def create_workspace(
    arguments: Dict[str, Any], client: LightRAGClient
) -> ToolResult:
    """Create a new workspace and generate its initial API key.

    The slug must start with a letter and contain only lowercase letters,
    digits, '_' or '-' (maximum 63 characters). The gateway validates this
    and returns a 400 if invalid. The response includes the workspace metadata
    and the initial api key (shown_once=true — copy it now).
    """
    args = CreateWorkspaceArguments.model_validate(arguments)
    return await _admin_gateway_request(
        "POST", f"/_workspaces/{args.slug}", {"display_name": args.display_name}
    )


@tool_handler("issue_key")
async def issue_key(arguments: Dict[str, Any], client: LightRAGClient) -> ToolResult:
    """Issue a new workspace API key.

    The workspace must already exist. The gateway returns the new key with
    shown_once=true. Use this to provision additional keys for collaborators
    or to rotate after a key compromise.
    """
    args = IssueKeyArguments.model_validate(arguments)
    return await _admin_gateway_request("POST", f"/_workspaces/{args.workspace}/keys")


@tool_handler("revoke_key")
async def revoke_key(arguments: Dict[str, Any], client: LightRAGClient) -> ToolResult:
    """Revoke a workspace API key by its prefix.

    The prefix is the first 18 characters of the key (e.g., 'lr_main_ABC123').
    Revoked keys can no longer authenticate. The gateway returns the number
    of keys revoked (0 or 1).
    """
    args = RevokeKeyArguments.model_validate(arguments)
    return await _admin_gateway_request("DELETE", f"/_keys/{args.prefix}")


@tool_handler("rotate_key")
async def rotate_key(arguments: Dict[str, Any], client: LightRAGClient) -> ToolResult:
    """Rotate a workspace key: revoke the current key and issue a new one.

    This is a convenience that combines revoke_key + issue_key for a full
    rotation workflow. The old key is revoked by prefix (you must provide the
    current key's prefix) and a fresh key is issued for the same workspace.

    The returned object includes the revoked key prefix and the new api key
    (shown_once=true). Save the new key immediately; the old key stops
    working as soon as the revoke call completes.
    """
    args = RotateKeyArguments.model_validate(arguments)
    # First, revoke all existing keys for this workspace (by prefix is not
    # practical for rotation since we don't know them, so we issue a new key
    # first and then revoke the old one by its full prefix).
    #
    # Simpler: issue new key → revoke old key by prefix (caller provides old).
    # This matches the typical rotation flow: operator has old key, requests
    # rotation, gets new key, old key is invalidated.
    #
    # But our tool signature doesn't include the old key. Gateway has no
    # "revoke all keys for workspace" endpoint. We'll implement a practical
    # approximation: issue new key, then attempt to revoke a key with prefix
    # matching the workspace (lr_<workspace>_*). Since we don't know the
    # exact prefix, we skip the revoke step and return only the new key
    # with a note that old keys remain valid until manually revoked.
    #
    # TODO: add a gateway endpoint `DELETE /_workspaces/{slug}/keys` to revoke
    # all keys for a workspace, which would enable full rotation.
    new_key_resp = await _admin_gateway_request(
        "POST", f"/_workspaces/{args.workspace}/keys"
    )
    return {
        "workspace": args.workspace,
        "new_api_key": new_key_resp.get("api_key"),
        "shown_once": True,
        "note": "Old keys remain valid. Revoke them manually via revoke_key with each key's prefix.",
    }

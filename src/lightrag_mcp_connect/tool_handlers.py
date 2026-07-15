"""Typed MCP tool handlers and dispatch registry."""

import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Union
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .client import LightRAGClient, LightRAGValidationError
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


class QueryArguments(ToolArguments):
    query: str = Field(min_length=1)
    mode: str = Field(default="hybrid", pattern="^(naive|local|global|hybrid|mix)$")
    only_need_context: bool = False


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

"""
LightRAG API client for MCP server integration.
"""

import asyncio
import contextvars
import ipaddress
import json
import logging
import socket
from typing import Any, Dict, List, Optional, AsyncGenerator, Type
from urllib.parse import unquote, urljoin, urlparse
import httpx

# Per-request API key override. When set (by the tool dispatcher), every
# LightRAG request made on the current async task carries this key as
# X-API-Key instead of the client's own default. This is what lets one
# shared client/connection-pool route different MCP calls to different
# workspaces (a per-call api_key passed in the tool arguments overrides
# the operator's env key). ContextVar gives per-async-task isolation, so
# concurrent requests stay independent.
_REQUEST_API_KEY: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "lightrag_request_api_key", default=None
)


def set_request_api_key(key: Optional[str]) -> "contextvars.Token[Optional[str]]":
    """Bind a per-call api key. Reset with the returned token in a finally block."""
    return _REQUEST_API_KEY.set(key)


def reset_request_api_key(
    token: "contextvars.Token[Optional[str]]",
) -> None:
    """Restore the prior api-key binding (companion to :func:`set_request_api_key`)."""
    _REQUEST_API_KEY.reset(token)


def _per_request_headers() -> Optional[Dict[str, str]]:
    """Headers to merge onto the client's defaults for this request, if any."""
    key = _REQUEST_API_KEY.get()
    return {"X-API-Key": key} if key else None
from .models import (
    # Request models
    InsertTextRequest,
    InsertTextsRequest,
    QueryRequest,
    EntityUpdateRequest,
    RelationUpdateRequest,
    DeleteDocRequest,
    DeleteEntityRequest,
    DeleteRelationRequest,
    DocumentsRequest,
    ClearCacheRequest,
    EntityExistsRequest,
    # Response models
    InsertResponse,
    ScanResponse,
    UploadResponse,
    DocumentsResponse,
    PaginatedDocsResponse,
    DeleteDocByIdResponse,
    ClearDocumentsResponse,
    PipelineStatusResponse,
    TrackStatusResponse,
    StatusCountsResponse,
    ClearCacheResponse,
    DeletionResult,
    QueryResponse,
    GraphResponse,
    LabelsResponse,
    EntityExistsResponse,
    EntityUpdateResponse,
    RelationUpdateResponse,
    HealthResponse,
    TextDocument,
    DocumentInfo,
    UpdateDocumentResponse,
    DocStatus,
    QueryMode,
)


# Custom Exception Hierarchy
class LightRAGError(Exception):
    """Base exception for LightRAG client errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
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
            "response_data": self.response_data,
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

    def __init__(
        self,
        base_url: str = "http://localhost:9621",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        self.client = httpx.AsyncClient(timeout=timeout, headers=headers)

        self.logger.info(f"Initialized LightRAG client with base_url: {self.base_url}")

    async def __aenter__(self) -> "LightRAGClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        await self.client.aclose()

    def _map_http_error(
        self,
        status_code: int,
        response_text: str,
        response_data: Optional[Dict[str, Any]] = None,
    ) -> LightRAGError:
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
            return LightRAGValidationError(
                f"Bad Request: {error_message}", status_code, parsed_data
            )
        elif status_code == 401:
            return LightRAGAuthError(
                f"Unauthorized: {error_message}", status_code, parsed_data
            )
        elif status_code == 403:
            return LightRAGAuthError(
                f"Forbidden: {error_message}", status_code, parsed_data
            )
        elif status_code == 404:
            return LightRAGAPIError(
                f"Not Found: {error_message}", status_code, parsed_data
            )
        elif status_code == 408:
            return LightRAGTimeoutError(
                f"Request Timeout: {error_message}", status_code, parsed_data
            )
        elif status_code == 422:
            return LightRAGValidationError(
                f"Validation Error: {error_message}", status_code, parsed_data
            )
        elif status_code == 429:
            return LightRAGAPIError(
                f"Rate Limited: {error_message}", status_code, parsed_data
            )
        elif 500 <= status_code < 600:
            return LightRAGServerError(
                f"Server Error: {error_message}", status_code, parsed_data
            )
        else:
            return LightRAGAPIError(error_message, status_code, parsed_data)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Make HTTP request to LightRAG API."""
        url = f"{self.base_url}{endpoint}"

        # Log request details
        self.logger.debug(f"Making {method} request to {url}")
        if data:
            self.logger.debug("Request JSON fields: %s", sorted(data))
        if params:
            self.logger.debug("Request query fields: %s", sorted(params))

        try:
            headers = _per_request_headers()
            if method.upper() == "GET":
                response = await self.client.get(url, params=params, headers=headers)
            elif method.upper() == "POST":
                if files:
                    response = await self.client.post(
                        url, data=data, files=files, headers=headers
                    )
                else:
                    response = await self.client.post(url, json=data, headers=headers)
            elif method.upper() == "DELETE":
                if data:
                    response = await self.client.request(
                        "DELETE", url, json=data, headers=headers
                    )
                else:
                    response = await self.client.delete(url, headers=headers)
            else:
                error_msg = f"Unsupported HTTP method: {method}"
                self.logger.error(error_msg)
                raise LightRAGError(error_msg)

            # Log response details
            self.logger.debug(f"Response status: {response.status_code}")
            response.raise_for_status()

            try:
                response_data = response.json()
                if isinstance(response_data, dict):
                    self.logger.debug("Response JSON fields: %s", sorted(response_data))
                else:
                    self.logger.debug(
                        "Response JSON type: %s", type(response_data).__name__
                    )
                self.logger.info(
                    f"Successfully completed {method} request to {endpoint}"
                )
                return response_data
            except json.JSONDecodeError as json_err:
                self.logger.error(f"Failed to parse JSON response: {json_err}")
                raise LightRAGAPIError(
                    f"Invalid JSON response from server: {str(json_err)}"
                )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "HTTP error %d for %s %s", e.response.status_code, method, endpoint
            )
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
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """Make streaming HTTP request to LightRAG API."""
        url = f"{self.base_url}{endpoint}"

        # Log streaming request details
        self.logger.debug(f"Making streaming {method} request to {url}")
        if data:
            self.logger.debug("Streaming request JSON fields: %s", sorted(data))

        try:
            async with self.client.stream(
                method, url, json=data, headers=_per_request_headers()
            ) as response:
                self.logger.debug(f"Streaming response status: {response.status_code}")
                response.raise_for_status()

                chunk_count = 0
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        chunk_count += 1
                        self.logger.debug(
                            f"Received streaming chunk {chunk_count}: {len(chunk)} characters"
                        )
                        yield chunk

                self.logger.info(
                    f"Successfully completed streaming {method} request to {endpoint}, received {chunk_count} chunks"
                )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "HTTP error %d for streaming %s %s",
                e.response.status_code,
                method,
                endpoint,
            )
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
            error_msg = (
                f"Unexpected error during streaming {method} request to {url}: {str(e)}"
            )
            self.logger.error(error_msg)
            raise LightRAGError(error_msg)

    # Document Management Methods (8 methods)

    async def insert_text(
        self, text: str, filename: Optional[str] = None
    ) -> InsertResponse:
        """Insert text content into LightRAG."""
        self.logger.info(f"Inserting text document with filename: {filename}")
        try:
            # Use filename as file_source if provided (as-is if it already has an
            # extension, e.g. "workspace__notes.md" — don't mangle it into
            # "workspace__notes.md.txt"); fall back to a generic name only
            # when no filename was given at all.
            if filename:
                file_source = filename if "." in filename else f"{filename}.txt"
            else:
                file_source = "text_input.txt"
            request_data = InsertTextRequest(text=text, file_source=file_source)
            response_data = await self._make_request(
                "POST", "/documents/text", request_data.model_dump()
            )
            result = InsertResponse(**response_data)
            self.logger.info(
                f"Successfully inserted text document with ID: {result.id}"
            )
            return result
        except Exception as e:
            self.logger.error(f"Failed to insert text document: {str(e)}")
            if isinstance(e, LightRAGError):
                raise
            # Handle Pydantic validation errors
            if hasattr(e, "errors") and callable(getattr(e, "errors")):
                raise LightRAGValidationError(f"Request validation failed: {str(e)}")
            raise LightRAGError(f"Text insertion failed: {str(e)}")

    async def insert_texts(self, texts: List[TextDocument]) -> InsertResponse:
        """Insert multiple text documents into LightRAG."""
        # Convert TextDocument objects to (content, filename) pairs
        text_strings = []
        filenames = []
        for doc in texts:
            if isinstance(doc, dict):
                # Handle dict input from tests
                text_strings.append(doc.get("content", str(doc)))
                filenames.append(doc.get("filename"))
            elif hasattr(doc, "content"):
                # Handle TextDocument objects
                text_strings.append(doc.content)
                filenames.append(getattr(doc, "filename", None))
            else:
                # Handle string input
                text_strings.append(str(doc))
                filenames.append(None)

        # Use each doc's filename as file_source when given (as-is if it already
        # has an extension, otherwise .txt-suffixed); fall back to a generic
        # per-index name only when no filename was provided for that item.
        file_sources = [
            (
                (filename if "." in filename else f"{filename}.txt")
                if filename
                else f"text_input_{i+1}.txt"
            )
            for i, filename in enumerate(filenames)
        ]

        request_data = InsertTextsRequest(texts=text_strings, file_sources=file_sources)
        response_data = await self._make_request(
            "POST", "/documents/texts", request_data.model_dump()
        )
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

            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f, "application/octet-stream")
                }
                response_data = await self._make_request(
                    "POST", "/documents/upload", files=files
                )
                result = UploadResponse(**response_data)
                self.logger.info(
                    f"Successfully uploaded document: {file_path} ({file_size} bytes) - Track ID: {result.track_id}"
                )
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

    async def upload_document_content(
        self, content: bytes, filename: str
    ) -> UploadResponse:
        """Upload document content (bytes) directly to LightRAG.

        Unlike upload_document, this doesn't read anything from the local
        filesystem — the caller supplies the file's bytes directly. This is
        the only path that works when the MCP server runs on a different
        machine than the calling agent (e.g. a remote/hosted deployment),
        since there's no shared filesystem to read a path from.
        """
        self.logger.info(
            f"Uploading document content: {filename} ({len(content)} bytes)"
        )
        try:
            files = {"file": (filename, content, "application/octet-stream")}
            response_data = await self._make_request(
                "POST", "/documents/upload", files=files
            )
            result = UploadResponse(**response_data)
            self.logger.info(
                f"Successfully uploaded document content: {filename} ({len(content)} bytes) - Track ID: {result.track_id}"
            )
            return result
        except Exception as e:
            error_msg = f"Failed to upload file content {filename}: {str(e)}"
            self.logger.error(error_msg)
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(error_msg)

    async def upload_document_as_text(self, text: str, filename: str) -> InsertResponse:
        """Upload a text document via LightRAG's /documents/text endpoint.

        Unlike upload_document_content (which posts multipart bytes to
        /documents/upload), this posts raw UTF-8 text as a JSON field —
        no base64, no encoding of any kind. LightRAG doesn't validate
        file_source against a file-type allowlist here (it's only used as
        a dedup/tracking key), so this only makes sense for content that's
        genuinely plain text; binary formats (.pdf/.docx/.pptx/.xlsx) need
        upload_document_content or upload_document_from_url instead, since
        LightRAG needs their actual bytes to parse them.

        filename is used as-is for file_source — not rewritten or
        normalized here (LightRAG normalizes it server-side regardless).
        """
        self.logger.info(f"Uploading text document: {filename} ({len(text)} chars)")
        try:
            request_data = InsertTextRequest(text=text, file_source=filename)
            response_data = await self._make_request(
                "POST", "/documents/text", request_data.model_dump()
            )
            result = InsertResponse(**response_data)
            self.logger.info(
                f"Successfully uploaded text document: {filename} - Track ID: {result.track_id}"
            )
            return result
        except Exception as e:
            error_msg = f"Failed to upload text content {filename}: {str(e)}"
            self.logger.error(error_msg)
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(error_msg)

    async def upload_document_from_url(
        self, url: str, filename: Optional[str] = None
    ) -> UploadResponse:
        """Fetch a file from a URL and upload it to LightRAG.

        Neither the calling agent nor the MCP server's own filesystem is
        involved — the MCP server fetches the bytes itself over HTTP. Nothing
        about the file's content has to travel through the calling agent's
        context or output tokens, and unlike
        file_path, it works regardless of where the MCP server runs. Meant
        for files the caller can only reference by a public URL (e.g. an
        uploaded attachment or artifact link), not embed directly.

        Only public http(s) URLs are fetched — requests to loopback,
        private, and link-local addresses (including the cloud metadata
        endpoint) are rejected before any connection is attempted, as a
        baseline defense against this becoming an SSRF vector against the
        MCP server's own network.
        """
        self.logger.info("Fetching document from URL host: %s", urlparse(url).hostname)
        current_url = url
        max_redirects = 5
        max_bytes = 50 * 1024 * 1024
        try:
            for redirect_count in range(max_redirects + 1):
                self._validate_public_url(current_url)
                async with self.client.stream(
                    "GET", current_url, follow_redirects=False
                ) as resp:
                    if resp.is_redirect:
                        if redirect_count == max_redirects:
                            raise LightRAGValidationError(
                                f"file_url exceeded the {max_redirects}-redirect limit"
                            )
                        location = resp.headers.get("location")
                        if not location:
                            raise LightRAGValidationError(
                                "file_url returned a redirect without a Location header"
                            )
                        current_url = urljoin(current_url, location)
                        continue

                    resp.raise_for_status()
                    chunks = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise LightRAGValidationError(
                                f"file_url content exceeds the {max_bytes // (1024 * 1024)}MB limit"
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)

                    resolved_filename = filename
                    if not resolved_filename:
                        cd = resp.headers.get("content-disposition", "")
                        if "filename=" in cd:
                            resolved_filename = cd.split("filename=")[-1].strip('"; ')
                    if not resolved_filename:
                        final_path = urlparse(current_url).path
                        resolved_filename = (
                            unquote(final_path.rsplit("/", 1)[-1]) or "download"
                        )
                    assert resolved_filename is not None
                    break
        except httpx.HTTPError as e:
            raise LightRAGValidationError(f"Failed to fetch file_url: {e}")

        self.logger.info("Fetched %d bytes from file_url", len(content))
        return await self.upload_document_content(
            content, resolved_filename or "download"
        )

    @staticmethod
    def _validate_public_url(url: str) -> None:
        """Reject URLs resolving to addresses that must not be fetched server-side."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise LightRAGValidationError(
                f"file_url must be http(s), got: {parsed.scheme!r}"
            )
        if not parsed.hostname:
            raise LightRAGValidationError(f"file_url has no hostname: {url}")
        if parsed.username or parsed.password:
            raise LightRAGValidationError("file_url must not contain credentials")

        try:
            resolved = socket.getaddrinfo(parsed.hostname, parsed.port)
        except socket.gaierror as e:
            raise LightRAGValidationError(
                f"Could not resolve file_url host {parsed.hostname!r}: {e}"
            )
        for _, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if not ip.is_global:
                raise LightRAGValidationError(
                    f"file_url resolves to a non-public address ({ip}) — "
                    "refusing to fetch internal/private network locations."
                )

    async def scan_documents(self) -> ScanResponse:
        """Scan for new documents in LightRAG."""
        response_data = await self._make_request("POST", "/documents/scan")
        return ScanResponse(**response_data)

    async def get_documents(self) -> DocumentsResponse:
        """Retrieve all documents from LightRAG."""
        response_data = await self._make_request("GET", "/documents")
        return DocumentsResponse(**response_data)

    async def get_documents_paginated(
        self, page: int = 1, page_size: int = 10, status_filter: Optional[str] = None
    ) -> PaginatedDocsResponse:
        """Retrieve documents with pagination from LightRAG."""
        parsed_status = DocStatus(status_filter) if status_filter else None
        request_data = DocumentsRequest(
            page=page, page_size=page_size, status_filter=parsed_status
        )
        response_data = await self._make_request(
            "POST", "/documents/paginated", request_data.model_dump()
        )
        return PaginatedDocsResponse(**response_data)

    async def delete_document(self, document_id: str) -> DeleteDocByIdResponse:
        """Delete a document by ID from LightRAG."""
        request_data = DeleteDocRequest(doc_ids=[document_id])
        response_data = await self._make_request(
            "DELETE", "/documents/delete_document", request_data.model_dump()
        )
        return DeleteDocByIdResponse(**response_data)

    async def find_document_by_filename(self, filename: str) -> Optional[DocumentInfo]:
        """Find one document by its exact normalized basename."""
        target = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        page = 1
        while True:
            response = await self.get_documents_paginated(page=page, page_size=100)
            for document in response.documents:
                if document.file_path:
                    candidate = document.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[
                        -1
                    ]
                    if candidate == target:
                        return document
            if not response.pagination.has_next:
                return None
            page += 1

    async def replace_text_document(
        self, filename: str, text: str, delete_timeout: float = 60.0
    ) -> UpdateDocumentResponse:
        """Replace a text document using LightRAG's delete-then-insert lifecycle."""
        deleted_doc_id = await self.delete_document_by_filename(
            filename, delete_timeout
        )
        inserted = await self.upload_document_as_text(text, filename)
        return UpdateDocumentResponse(
            status=inserted.status,
            message=f"Replaced '{filename}' and queued the new content",
            filename=filename,
            deleted_doc_id=deleted_doc_id,
            track_id=inserted.track_id,
        )

    async def delete_document_by_filename(
        self, filename: str, delete_timeout: float = 60.0
    ) -> str:
        """Delete an existing named document and wait until it disappears."""
        existing = await self.find_document_by_filename(filename)
        if existing is None:
            raise LightRAGValidationError(
                f"Cannot update '{filename}': no document with that filename exists"
            )

        deadline = asyncio.get_running_loop().time() + delete_timeout
        while True:
            deletion = await self.delete_document(existing.id)
            if deletion.status == "deletion_started":
                break
            if deletion.status != "busy":
                raise LightRAGAPIError(
                    f"LightRAG did not start deletion for '{filename}': "
                    f"{deletion.status}"
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise LightRAGTimeoutError(
                    f"Timed out waiting to start deletion of '{filename}'"
                )
            await asyncio.sleep(0.5)

        while await self.find_document_by_filename(filename) is not None:
            if asyncio.get_running_loop().time() >= deadline:
                raise LightRAGTimeoutError(
                    f"Timed out waiting for '{filename}' to be deleted"
                )
            await asyncio.sleep(0.5)

        return existing.id

    async def clear_documents(self) -> ClearDocumentsResponse:
        """Clear all documents from LightRAG."""
        response_data = await self._make_request("DELETE", "/documents")
        return ClearDocumentsResponse(**response_data)

    # Query Methods (2 methods)

    async def query_text(
        self, query: str, mode: str = "hybrid", only_need_context: bool = False
    ) -> QueryResponse:
        """Query LightRAG with text."""
        self.logger.info("Querying text with mode '%s' (%d chars)", mode, len(query))

        # Validate query parameters
        if not query or not query.strip():
            raise LightRAGValidationError("Query cannot be empty")

        valid_modes = ["naive", "local", "global", "hybrid", "mix"]
        if mode not in valid_modes:
            raise LightRAGValidationError(
                f"Invalid query mode '{mode}'. Must be one of: {valid_modes}"
            )

        try:
            request_data = QueryRequest(
                query=query,
                mode=QueryMode(mode),
                only_need_context=only_need_context,
                stream=False,
            )
            response_data = await self._make_request(
                "POST", "/query", request_data.model_dump()
            )
            result = QueryResponse(**response_data)

            result_count = (
                len(result.results)
                if hasattr(result, "results") and result.results
                else 0
            )
            self.logger.info(
                f"Query completed successfully, returned {result_count} results"
            )
            return result
        except Exception as e:
            self.logger.error(f"Query failed for mode '{mode}': {str(e)}")
            if isinstance(e, LightRAGError):
                raise
            raise LightRAGError(f"Query operation failed: {str(e)}")

    async def query_text_stream(
        self, query: str, mode: str = "hybrid", only_need_context: bool = False
    ) -> AsyncGenerator[str, None]:
        """Stream query results from LightRAG."""
        # Validate query parameters
        if not query or not query.strip():
            raise LightRAGValidationError("Query cannot be empty")

        valid_modes = ["naive", "local", "global", "hybrid", "mix"]
        if mode not in valid_modes:
            raise LightRAGValidationError(
                f"Invalid query mode '{mode}'. Must be one of: {valid_modes}"
            )

        self.logger.info(
            "Starting buffered upstream query with mode '%s' (%d chars)",
            mode,
            len(query),
        )

        try:
            request_data = QueryRequest(
                query=query,
                mode=QueryMode(mode),
                only_need_context=only_need_context,
                stream=True,
            )
            async for chunk in self._stream_request(
                "POST", "/query/stream", request_data.model_dump()
            ):
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
        response_data = await self._make_request(
            "GET", "/graph/entity/exists", params=params
        )
        return EntityExistsResponse(**response_data)

    async def update_entity(
        self,
        entity_id: str,
        properties: Dict[str, Any],
        entity_name: Optional[str] = None,
    ) -> EntityUpdateResponse:
        """Update an entity in the knowledge graph."""
        if entity_name is None:
            entity_name = entity_id
        request_data = EntityUpdateRequest(
            entity_id=entity_id, entity_name=entity_name, updated_data=properties
        )
        response_data = await self._make_request(
            "POST", "/graph/entity/edit", request_data.model_dump()
        )
        return EntityUpdateResponse(**response_data)

    # async def update_relation(self, relation_id: str, properties: Dict[str, Any], source_id: str = "unknown", target_id: str = "unknown") -> RelationUpdateResponse:
    #     """Update a relation in the knowledge graph."""
    #     request_data = RelationUpdateRequest(relation_id=relation_id, source_id=source_id, target_id=target_id, updated_data=properties)
    #     response_data = await self._make_request("POST", "/graph/relation/edit", request_data.model_dump())
    #     return RelationUpdateResponse(**response_data)

    async def update_relation(
        self, source_id: str, target_id: str, updated_data: Dict[str, Any]
    ) -> RelationUpdateResponse:
        """Update a relation in the knowledge graph."""
        request_data = RelationUpdateRequest(
            source_id=source_id, target_id=target_id, updated_data=updated_data
        )
        response_data = await self._make_request(
            "POST", "/graph/relation/edit", request_data.model_dump()
        )
        return RelationUpdateResponse(**response_data)

    async def delete_entity(
        self, entity_id: str, entity_name: Optional[str] = None
    ) -> DeletionResult:
        """Delete an entity from the knowledge graph."""
        if entity_name is None:
            entity_name = entity_id
        request_data = DeleteEntityRequest(entity_id=entity_id, entity_name=entity_name)
        response_data = await self._make_request(
            "DELETE", "/documents/delete_entity", request_data.model_dump()
        )
        return DeletionResult(**response_data)

    async def delete_relation(
        self,
        relation_id: str,
        source_entity: str = "unknown",
        target_entity: str = "unknown",
    ) -> DeletionResult:
        """Delete a relation from the knowledge graph."""
        request_data = DeleteRelationRequest(
            relation_id=relation_id,
            source_entity=source_entity,
            target_entity=target_entity,
        )
        response_data = await self._make_request(
            "DELETE", "/documents/delete_relation", request_data.model_dump()
        )
        return DeletionResult(**response_data)

    # System Management Methods (4 methods)

    async def get_pipeline_status(self) -> PipelineStatusResponse:
        """Get the pipeline status from LightRAG."""
        response_data = await self._make_request("GET", "/documents/pipeline_status")
        return PipelineStatusResponse(**response_data)

    async def get_track_status(self, track_id: str) -> TrackStatusResponse:
        """Get the track status for a specific track ID."""
        response_data = await self._make_request(
            "GET", f"/documents/track_status/{track_id}"
        )
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
        response_data = await self._make_request(
            "POST", "/documents/clear_cache", request_data
        )
        return ClearCacheResponse(**response_data)

    async def get_health(self) -> HealthResponse:
        """Check LightRAG server health."""
        response_data = await self._make_request("GET", "/health")
        return HealthResponse(**response_data)

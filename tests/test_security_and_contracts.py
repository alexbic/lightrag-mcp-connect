import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lightrag_mcp_connect.client import LightRAGClient, LightRAGValidationError
from lightrag_mcp_connect.models import LabelsResponse
from lightrag_mcp_connect.server import (
    _SensitivePayloadFilter,
    _resolve_allowed_file_path,
    _validate_tool_arguments,
    handle_list_tools,
)


def test_sensitive_payload_filter_drops_payload_logs() -> None:
    log_filter = _SensitivePayloadFilter()
    sensitive = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "  - Raw arguments: {'text': 'private document'}",
        (),
        None,
    )
    safe = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "Tool completed in 20 ms", (), None
    )

    assert log_filter.filter(sensitive) is False
    assert log_filter.filter(safe) is True


def test_upload_requires_exactly_one_source() -> None:
    with pytest.raises(LightRAGValidationError, match="exactly one source"):
        _validate_tool_arguments(
            "upload_document",
            {
                "text_content": "hello",
                "file_url": "https://example.com/hello.txt",
                "filename": "hello.txt",
            },
        )


def test_file_path_is_disabled_without_root(tmp_path: Path) -> None:
    document = tmp_path / "document.txt"
    document.write_text("private", encoding="utf-8")

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(LightRAGValidationError, match="disabled"):
            _resolve_allowed_file_path(str(document))


def test_file_path_must_stay_inside_configured_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    inside = allowed / "inside.txt"
    outside = tmp_path / "outside.txt"
    inside.write_text("inside", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")

    with patch.dict("os.environ", {"LIGHTRAG_FILE_PATH_ROOT": str(allowed)}):
        assert _resolve_allowed_file_path(str(inside)) == inside.resolve()
        with pytest.raises(LightRAGValidationError, match="must be inside"):
            _resolve_allowed_file_path(str(outside))


def test_private_url_is_rejected() -> None:
    with patch(
        "lightrag_mcp_connect.client.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("127.0.0.1", 80))],
    ):
        with pytest.raises(LightRAGValidationError, match="non-public"):
            LightRAGClient._validate_public_url("http://example.test/file.pdf")


@pytest.mark.asyncio
async def test_redirect_target_is_validated_before_second_request() -> None:
    requested_urls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/metadata"})

    client = LightRAGClient()
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with patch.object(
            client,
            "_validate_public_url",
            side_effect=[None, LightRAGValidationError("non-public redirect")],
        ):
            with pytest.raises(LightRAGValidationError, match="non-public redirect"):
                await client.upload_document_from_url("https://public.example/file.pdf")
    finally:
        await client.client.aclose()

    assert requested_urls == ["https://public.example/file.pdf"]


@pytest.mark.asyncio
async def test_graph_label_list_is_preserved() -> None:
    client = LightRAGClient()
    await client.client.aclose()
    client._make_request = AsyncMock(return_value=["PERSON", "ORGANIZATION"])

    result = await client.get_graph_labels()

    assert result.model_dump() == {"labels": ["PERSON", "ORGANIZATION"]}
    assert result.entity_labels == ["PERSON", "ORGANIZATION"]
    assert result.relation_labels == []


def test_labels_response_contract() -> None:
    response = LabelsResponse(labels=["PERSON"])
    assert response.model_dump() == {"labels": ["PERSON"]}


@pytest.mark.asyncio
async def test_buffered_stream_tool_is_not_advertised() -> None:
    tools = await handle_list_tools()
    assert "query_text_stream" not in {tool.name for tool in tools}

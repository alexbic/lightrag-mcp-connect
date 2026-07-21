from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from lightrag_mcp_connect.client import LightRAGClient, LightRAGValidationError
from lightrag_mcp_connect.models import (
    DeleteDocByIdResponse,
    DocStatus,
    DocumentInfo,
    InsertResponse,
    UploadResponse,
)
from lightrag_mcp_connect.server import handle_call_tool_refactored, handle_list_tools
from lightrag_mcp_connect.tool_handlers import (
    TOOL_HANDLERS,
    append_text,
    update_document,
)


def processed_document(filename: str = "notes.md") -> DocumentInfo:
    return DocumentInfo(id="doc-1", file_path=filename, status=DocStatus.PROCESSED)


@pytest.mark.asyncio
async def test_advertised_tools_have_registered_handlers() -> None:
    tools = await handle_list_tools()
    advertised = {tool.name for tool in tools}
    # All advertised tools must have registered handlers
    assert advertised.issubset(TOOL_HANDLERS), "Advertised tools without handlers"
    assert not {"insert_text", "insert_texts"} & advertised
    for name in ("upload_document", "update_document", "append_text"):
        schema = next(tool.inputSchema for tool in tools if tool.name == name)
        assert next(iter(schema["properties"])) == "filename"

    # Admin tools are only advertised in gateway mode with an admin key.
    # Handlers exist regardless (for gateway activations), so we don't
    # require exact equality — just that unadvertised handlers are either
    # admin tools or we're in simple mode.
    admin_tools = {"create_workspace", "issue_key", "revoke_key", "rotate_key"}
    unadvertised = set(TOOL_HANDLERS) - advertised
    if unadvertised:
        # If anything is missing from the advertised list, it must be admin tools
        # (and we're likely running in simple mode without LIGHTRAG_GATEWAY_URL).
        assert unadvertised.issubset(
            admin_tools
        ), f"Unadvertised non-admin tools: {unadvertised}"


@pytest.mark.asyncio
async def test_unknown_tool_is_a_real_mcp_error() -> None:
    result = await handle_call_tool_refactored("insert_text", {})
    assert result.isError is True


@pytest.mark.asyncio
async def test_graph_labels_accepts_lightrag_list_response() -> None:
    client = LightRAGClient()
    await client.client.aclose()
    client._make_request = AsyncMock(return_value=["PERSON", "PROJECT"])
    result = await client.get_graph_labels()
    assert result.labels == ["PERSON", "PROJECT"]


@pytest.mark.asyncio
async def test_update_inline_uses_filename_then_text_content(tmp_path: Path) -> None:
    client = AsyncMock(spec=LightRAGClient)
    client.delete_document_by_filename.return_value = "doc-1"
    client.upload_document_as_text.return_value = InsertResponse(
        status="success", message="queued", track_id="insert-1"
    )
    with patch.dict(
        "os.environ", {"LIGHTRAG_MCP_CONTENT_DB": str(tmp_path / "content.sqlite3")}
    ):
        result = await update_document(
            {"filename": "notes.md", "text_content": "replacement"}, client
        )

    assert result.filename == "notes.md"
    client.delete_document_by_filename.assert_awaited_once_with("notes.md", 60.0)
    client.upload_document_as_text.assert_awaited_once_with("replacement", "notes.md")


@pytest.mark.asyncio
async def test_update_file_path_derives_filename(tmp_path: Path) -> None:
    document = tmp_path / "report.pdf"
    document.write_bytes(b"pdf")
    client = AsyncMock(spec=LightRAGClient)
    client.delete_document_by_filename.return_value = "doc-1"
    client.upload_document.return_value = UploadResponse(
        status="success", message="queued", track_id="upload-1"
    )
    with patch.dict(
        "os.environ",
        {
            "LIGHTRAG_FILE_PATH_ROOT": str(tmp_path),
            "LIGHTRAG_MCP_CONTENT_DB": str(tmp_path / "content.sqlite3"),
        },
    ):
        result = await update_document({"file_path": str(document)}, client)

    assert result.filename == "report.pdf"
    client.delete_document_by_filename.assert_awaited_once_with("report.pdf", 60.0)
    client.upload_document.assert_awaited_once_with(str(document))


@pytest.mark.asyncio
async def test_update_file_url_derives_filename(tmp_path: Path) -> None:
    client = AsyncMock(spec=LightRAGClient)
    client.delete_document_by_filename.return_value = "doc-1"
    client.upload_document_from_url.return_value = UploadResponse(
        status="success", message="queued", track_id="upload-1"
    )
    with patch.dict(
        "os.environ", {"LIGHTRAG_MCP_CONTENT_DB": str(tmp_path / "content.sqlite3")}
    ):
        result = await update_document(
            {"file_url": "https://example.com/files/report.pdf"}, client
        )

    assert result.filename == "report.pdf"
    client.delete_document_by_filename.assert_awaited_once_with("report.pdf", 60.0)
    client.upload_document_from_url.assert_awaited_once_with(
        "https://example.com/files/report.pdf"
    )


@pytest.mark.asyncio
async def test_replace_document_waits_for_delete_then_inserts() -> None:
    client = LightRAGClient()
    await client.client.aclose()
    client.find_document_by_filename = AsyncMock(
        side_effect=[processed_document(), processed_document(), None]
    )
    client.delete_document = AsyncMock(
        return_value=DeleteDocByIdResponse(
            status="deletion_started", message="queued", doc_id="doc-1"
        )
    )
    client.upload_document_as_text = AsyncMock(
        return_value=InsertResponse(
            status="success", message="queued", track_id="insert-1"
        )
    )

    with patch("lightrag_mcp_connect.client.asyncio.sleep", new=AsyncMock()):
        result = await client.replace_text_document("notes.md", "replacement")

    assert result.deleted_doc_id == "doc-1"
    assert result.track_id == "insert-1"
    client.upload_document_as_text.assert_awaited_once_with("replacement", "notes.md")


@pytest.mark.asyncio
async def test_replace_requires_existing_document() -> None:
    client = LightRAGClient()
    await client.client.aclose()
    client.find_document_by_filename = AsyncMock(return_value=None)

    with pytest.raises(LightRAGValidationError, match="no document"):
        await client.replace_text_document("missing.md", "replacement")


@pytest.mark.asyncio
async def test_replace_retries_while_pipeline_is_busy() -> None:
    client = LightRAGClient()
    await client.client.aclose()
    client.find_document_by_filename = AsyncMock(
        side_effect=[processed_document(), processed_document(), None]
    )
    client.delete_document = AsyncMock(
        side_effect=[
            DeleteDocByIdResponse(status="busy", message="processing", doc_id="doc-1"),
            DeleteDocByIdResponse(
                status="deletion_started", message="queued", doc_id="doc-1"
            ),
        ]
    )
    client.upload_document_as_text = AsyncMock(
        return_value=InsertResponse(
            status="success", message="queued", track_id="insert-1"
        )
    )

    with patch("lightrag_mcp_connect.client.asyncio.sleep", new=AsyncMock()):
        await client.replace_text_document("notes.md", "replacement")

    assert client.delete_document.await_count == 2


@pytest.mark.asyncio
async def test_append_uses_exact_mirrored_source(tmp_path: Path) -> None:
    database = tmp_path / "content.sqlite3"
    client = AsyncMock(spec=LightRAGClient)
    client.find_document_by_filename.return_value = processed_document()
    client.replace_text_document.return_value = type(
        "UpdateResult",
        (),
        {
            "status": "success",
            "deleted_doc_id": "doc-1",
            "track_id": "insert-2",
        },
    )()

    with patch.dict("os.environ", {"LIGHTRAG_MCP_CONTENT_DB": str(database)}):
        from lightrag_mcp_connect.content_store import DocumentContentStore

        DocumentContentStore().put("notes.md", "first")
        result = await append_text(
            {"filename": "notes.md", "text_content": "second"}, client
        )
        assert DocumentContentStore().get("notes.md") == "first\nsecond"

    assert result.appended_characters == 6
    client.replace_text_document.assert_awaited_once_with(
        filename="notes.md", text="first\nsecond", delete_timeout=60.0
    )


@pytest.mark.asyncio
async def test_append_rejects_unmanaged_source(tmp_path: Path) -> None:
    client = AsyncMock(spec=LightRAGClient)
    client.find_document_by_filename.return_value = processed_document()
    with patch.dict(
        "os.environ", {"LIGHTRAG_MCP_CONTENT_DB": str(tmp_path / "empty.sqlite3")}
    ):
        with pytest.raises(LightRAGValidationError, match="not managed"):
            await append_text(
                {"filename": "notes.md", "text_content": "second"}, client
            )

"""
test_mcp_server.py — MCP knowledge server 测试
"""

import json
import pytest

from rag.mcp.knowledge_server import (
    PACK_ID_RE,
    _require_pack_id,
)


class TestMCPUtils:
    def test_pack_id_re_valid(self):
        assert PACK_ID_RE.match("deslop")
        assert PACK_ID_RE.match("topic-survival")
        assert PACK_ID_RE.match("a0-z9-123")

    def test_pack_id_re_invalid(self):
        assert not PACK_ID_RE.match("")
        assert not PACK_ID_RE.match("with space")
        assert not PACK_ID_RE.match("UPPERCASE")
        assert not PACK_ID_RE.match("中文")
        assert not PACK_ID_RE.match("-leading")
        assert not PACK_ID_RE.match("trailing-")

    def test_require_pack_id_valid(self):
        assert _require_pack_id({"pack_id": "valid-pack"}) == "valid-pack"

    def test_require_pack_id_invalid(self):
        with pytest.raises(ValueError):
            _require_pack_id({"pack_id": "INVALID"})

    def test_require_pack_id_missing(self):
        with pytest.raises(ValueError):
            _require_pack_id({})


class TestMCPLegacyMode:
    """测试旧版兼容模式的核心 JSON-RPC 处理"""

    def test_initialize_response(self):
        from rag.mcp.knowledge_server import _handle as handle
        resp = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"]["serverInfo"]["name"] == "novel-harness-knowledge"

    def test_tools_list_response(self):
        from rag.mcp.knowledge_server import _handle as handle
        resp = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert resp["jsonrpc"] == "2.0"
        assert "result" in resp
        assert "tools" in resp["result"]
        tools = resp["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        assert "list_knowledge_packs" in tool_names
        assert "install_knowledge_pack" in tool_names

    def test_unknown_method(self):
        from rag.mcp.knowledge_server import _handle as handle
        resp = handle({"jsonrpc": "2.0", "id": 3, "method": "unknown"})
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_notifications_initialized(self):
        from rag.mcp.knowledge_server import _handle as handle
        resp = handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp is None

    def test_tools_call_unknown(self):
        from rag.mcp.knowledge_server import _handle as handle
        resp = handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nonexistent_tool"},
        })
        assert "error" in resp

"""
knowledge_server.py — MCP stdio 服务（基于官方 mcp SDK）

暴露 7 个 tools 用于管理远程知识包：
  list_knowledge_packs, list_knowledge_pack_types, list_installed_packs,
  install_knowledge_pack, update_knowledge_pack, remove_knowledge_pack,
  rebuild_rag_index
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent, CallToolResult

    # mcp SDK 1.x 里 stdio_server 位于 mcp.server.stdio，
    # 部分旧版本才把它再导出到 mcp.server；两种位置都兼容一下。
    try:
        from mcp.server.stdio import stdio_server
    except ImportError:  # pragma: no cover - 兼容旧版 SDK
        from mcp.server import stdio_server  # type: ignore[attr-defined]

    HAS_MCP_SDK = True
except ImportError:
    HAS_MCP_SDK = False


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SYNC_SCRIPT = PROJECT_ROOT / "rag" / "scripts" / "sync_packs.py"
# 小写字母/数字 + 中间连字符，且首尾必须是字母或数字（不能以连字符开头或结尾）。
# 旧写法 ^[a-z0-9][a-z0-9-]{0,48}$ 会接受 "trailing-" 这种畸形 id。
PACK_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,47}[a-z0-9])?$")
PACK_ID_HINT = "pack_id 只能由小写字母、数字和连字符组成，长度不超过 49，且不能以连字符开头或结尾"


def _manifest_arg(arguments: dict[str, Any]) -> list[str]:
    manifest = arguments.get("manifest_url") or os.environ.get("NOVEL_HARNESS_REMOTE_MANIFEST")
    return ["--manifest", str(manifest)] if manifest else []


def _run_sync(args: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _require_pack_id(arguments: dict[str, Any]) -> str:
    pack_id = str(arguments.get("pack_id", "")).strip()
    if not PACK_ID_RE.match(pack_id):
        raise ValueError(PACK_ID_HINT)
    return pack_id


async def handle_list_knowledge_packs(arguments: dict[str, Any]) -> dict[str, Any]:
    include_remote = bool(arguments.get("include_remote", True))
    args = [*_manifest_arg(arguments), "--json", "list"]
    if include_remote:
        args.append("--include-remote")
    pack_type = str(arguments.get("pack_type", "")).strip()
    if pack_type:
        args.extend(["--type", pack_type])
    return _run_sync(args)


async def handle_list_knowledge_pack_types(arguments: dict[str, Any]) -> dict[str, Any]:
    args = [*_manifest_arg(arguments), "--json", "types"]
    return _run_sync(args)


async def handle_list_installed_packs(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run_sync(["--json", "installed"])


async def handle_install_knowledge_pack(arguments: dict[str, Any]) -> dict[str, Any]:
    pack_id = _require_pack_id(arguments)
    rebuild_index = bool(arguments.get("rebuild_index", True))
    args = [*_manifest_arg(arguments), "install", pack_id]
    pack_type = str(arguments.get("pack_type", "")).strip()
    if pack_type:
        args.extend(["--type", pack_type])
    if rebuild_index:
        args.append("--rebuild-index")
    return _run_sync(args)


async def handle_update_knowledge_pack(arguments: dict[str, Any]) -> dict[str, Any]:
    pack_id = _require_pack_id(arguments)
    rebuild_index = bool(arguments.get("rebuild_index", True))
    args = [*_manifest_arg(arguments), "update", pack_id]
    pack_type = str(arguments.get("pack_type", "")).strip()
    if pack_type:
        args.extend(["--type", pack_type])
    if rebuild_index:
        args.append("--rebuild-index")
    return _run_sync(args)


async def handle_remove_knowledge_pack(arguments: dict[str, Any]) -> dict[str, Any]:
    pack_id = _require_pack_id(arguments)
    rebuild_index = bool(arguments.get("rebuild_index", True))
    args = ["remove", pack_id]
    if rebuild_index:
        args.append("--rebuild-index")
    return _run_sync(args)


async def handle_rebuild_rag_index(arguments: dict[str, Any]) -> dict[str, Any]:
    return _run_sync(["rebuild-index"])


class MCPKnwoledgeServer:
    def __init__(self):
        self.server = Server("novel-harness-knowledge")
        self._register_tools()

    def _register_tools(self):
        srv = self.server

        @srv.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="list_knowledge_packs",
                    description=(
                        "列出内置和远程知识包。可选按类型过滤。"
                        "如果不确定需要哪个包，先用此工具查看可用选项。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "manifest_url": {
                                "type": "string",
                                "description": "可选：远程 manifest URL，未传时读取 NOVEL_HARNESS_REMOTE_MANIFEST（.env 或环境变量）",
                            },
                            "include_remote": {
                                "type": "boolean",
                                "default": True,
                                "description": "是否包含远程知识包",
                            },
                            "pack_type": {
                                "type": "string",
                                "description": "可选过滤：topic, writing, design, polish, workflow 等",
                            },
                        },
                    },
                ),
                Tool(
                    name="list_knowledge_pack_types",
                    description="列出远程知识包的类型分类",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "manifest_url": {
                                "type": "string",
                                "description": "可选：远程 manifest URL",
                            },
                        },
                    },
                ),
                Tool(
                    name="list_installed_packs",
                    description="列出已安装的远程知识包",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="install_knowledge_pack",
                    description="安装远程知识包到本地 .harness/knowledge/remote/",
                    inputSchema={
                        "type": "object",
                        "required": ["pack_id"],
                        "properties": {
                            "pack_id": {
                                "type": "string",
                                "description": "知识包 ID（来自 list_knowledge_packs）",
                            },
                            "manifest_url": {
                                "type": "string",
                                "description": "可选：远程 manifest URL",
                            },
                            "pack_type": {
                                "type": "string",
                                "description": "可选：知识包类型，用于缩小 manifest 查找范围",
                            },
                            "rebuild_index": {
                                "type": "boolean",
                                "default": True,
                                "description": "安装后是否重建 RAG 索引",
                            },
                        },
                    },
                ),
                Tool(
                    name="update_knowledge_pack",
                    description="更新已安装的知识包（重新下载安装）",
                    inputSchema={
                        "type": "object",
                        "required": ["pack_id"],
                        "properties": {
                            "pack_id": {"type": "string"},
                            "manifest_url": {"type": "string"},
                            "pack_type": {"type": "string"},
                            "rebuild_index": {
                                "type": "boolean",
                                "default": True,
                            },
                        },
                    },
                ),
                Tool(
                    name="remove_knowledge_pack",
                    description="移除已安装的远程知识包",
                    inputSchema={
                        "type": "object",
                        "required": ["pack_id"],
                        "properties": {
                            "pack_id": {"type": "string"},
                            "rebuild_index": {
                                "type": "boolean",
                                "default": True,
                            },
                        },
                    },
                ),
                Tool(
                    name="rebuild_rag_index",
                    description="重建本地 RAG 索引（扫描所有知识文件并重新构建）",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @srv.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            handlers = {
                "list_knowledge_packs": handle_list_knowledge_packs,
                "list_knowledge_pack_types": handle_list_knowledge_pack_types,
                "list_installed_packs": handle_list_installed_packs,
                "install_knowledge_pack": handle_install_knowledge_pack,
                "update_knowledge_pack": handle_update_knowledge_pack,
                "remove_knowledge_pack": handle_remove_knowledge_pack,
                "rebuild_rag_index": handle_rebuild_rag_index,
            }

            handler = handlers.get(name)
            if not handler:
                raise ValueError(f"Unknown tool: {name}")

            try:
                payload = await handler(arguments or {})
            except Exception as exc:
                payload = {"exit_code": 1, "stdout": "", "stderr": str(exc)}

            is_error = payload.get("exit_code", 1) != 0
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            return [TextContent(type="text", text=text)]

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())


def _handle(message: dict[str, Any]) -> dict[str, Any] | None:
    """处理单个 JSON-RPC 消息（兼容旧版协议模式）"""
    method = message.get("method")
    request_id = message.get("id")

    handlers = {
        "list_knowledge_packs": handle_list_knowledge_packs,
        "list_knowledge_pack_types": handle_list_knowledge_pack_types,
        "list_installed_packs": handle_list_installed_packs,
        "install_knowledge_pack": handle_install_knowledge_pack,
        "update_knowledge_pack": handle_update_knowledge_pack,
        "remove_knowledge_pack": handle_remove_knowledge_pack,
        "rebuild_rag_index": handle_rebuild_rag_index,
    }

    TOOL_DEFS = {
        "list_knowledge_packs": {"description": "List built-in and server-provided knowledge packs.", "inputSchema": {"type": "object", "properties": {"manifest_url": {"type": "string"}, "include_remote": {"type": "boolean", "default": True}, "pack_type": {"type": "string"}}}},
        "list_knowledge_pack_types": {"description": "List server-provided knowledge pack types.", "inputSchema": {"type": "object", "properties": {"manifest_url": {"type": "string"}}}},
        "list_installed_packs": {"description": "List installed packs.", "inputSchema": {"type": "object", "properties": {}}},
        "install_knowledge_pack": {"description": "Install a knowledge pack.", "inputSchema": {"type": "object", "required": ["pack_id"], "properties": {"pack_id": {"type": "string"}, "manifest_url": {"type": "string"}, "pack_type": {"type": "string"}, "rebuild_index": {"type": "boolean", "default": True}}}},
        "update_knowledge_pack": {"description": "Update a knowledge pack.", "inputSchema": {"type": "object", "required": ["pack_id"], "properties": {"pack_id": {"type": "string"}, "manifest_url": {"type": "string"}, "pack_type": {"type": "string"}, "rebuild_index": {"type": "boolean", "default": True}}}},
        "remove_knowledge_pack": {"description": "Remove a knowledge pack.", "inputSchema": {"type": "object", "required": ["pack_id"], "properties": {"pack_id": {"type": "string"}, "rebuild_index": {"type": "boolean", "default": True}}}},
        "rebuild_rag_index": {"description": "Rebuild the local RAG index.", "inputSchema": {"type": "object", "properties": {}}},
    }

    if method == "initialize":
        params = message.get("params") or {}
        return {
            "jsonrpc": "2.0", "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "novel-harness-knowledge", "version": "0.2.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        tools_list = [{"name": n, **d} for n, d in TOOL_DEFS.items()]
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools_list}}

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = handlers.get(name)
        if not handler:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        import asyncio
        try:
            payload = asyncio.run(handler(args))
        except Exception as exc:
            payload = {"exit_code": 1, "stdout": "", "stderr": str(exc)}
        is_error = payload.get("exit_code", 1) != 0
        return {
            "jsonrpc": "2.0", "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "isError": is_error,
            },
        }

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main_legacy():
    """兼容旧版直接 stdin/stdout 模式（当 mcp SDK 不可用时）"""
    print("[knowledge_server] mcp SDK 不可用，使用兼容协议模式", file=sys.stderr)

    TOOLS = {
        "list_knowledge_packs": handle_list_knowledge_packs,
        "list_knowledge_pack_types": handle_list_knowledge_pack_types,
        "list_installed_packs": handle_list_installed_packs,
        "install_knowledge_pack": handle_install_knowledge_pack,
        "update_knowledge_pack": handle_update_knowledge_pack,
        "remove_knowledge_pack": handle_remove_knowledge_pack,
        "rebuild_rag_index": handle_rebuild_rag_index,
    }

    TOOL_DEFS = {
        "list_knowledge_packs": {
            "description": "List built-in and server-provided knowledge packs.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "manifest_url": {"type": "string"},
                    "include_remote": {"type": "boolean", "default": True},
                    "pack_type": {"type": "string"},
                },
            },
        },
        "list_knowledge_pack_types": {
            "description": "List server-provided knowledge pack types.",
            "inputSchema": {"type": "object", "properties": {"manifest_url": {"type": "string"}}},
        },
        "list_installed_packs": {
            "description": "List installed packs.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        "install_knowledge_pack": {
            "description": "Install a knowledge pack.",
            "inputSchema": {
                "type": "object",
                "required": ["pack_id"],
                "properties": {
                    "pack_id": {"type": "string"},
                    "manifest_url": {"type": "string"},
                    "pack_type": {"type": "string"},
                    "rebuild_index": {"type": "boolean", "default": True},
                },
            },
        },
        "update_knowledge_pack": {
            "description": "Update a knowledge pack.",
            "inputSchema": {
                "type": "object",
                "required": ["pack_id"],
                "properties": {
                    "pack_id": {"type": "string"},
                    "manifest_url": {"type": "string"},
                    "pack_type": {"type": "string"},
                    "rebuild_index": {"type": "boolean", "default": True},
                },
            },
        },
        "remove_knowledge_pack": {
            "description": "Remove a knowledge pack.",
            "inputSchema": {
                "type": "object",
                "required": ["pack_id"],
                "properties": {"pack_id": {"type": "string"}, "rebuild_index": {"type": "boolean", "default": True}},
            },
        },
        "rebuild_rag_index": {
            "description": "Rebuild the local RAG index.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    }

    import asyncio

    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        rid = msg.get("id")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "novel-harness-knowledge", "version": "0.2.0"},
                },
            }
        elif method == "notifications/initialized":
            resp = None
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {}}
        elif method == "tools/list":
            tools_list = [{"name": n, **d} for n, d in TOOL_DEFS.items()]
            resp = {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools_list}}
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            handler = TOOLS.get(name)
            if not handler:
                resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
            else:
                try:
                    payload = asyncio.run(handler(args))
                except Exception as exc:
                    payload = {"exit_code": 1, "stdout": "", "stderr": str(exc)}
                is_error = payload.get("exit_code", 1) != 0
                resp = {
                    "jsonrpc": "2.0", "id": rid,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                        "isError": is_error,
                    },
                }
        else:
            resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}

        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)


def main():
    if not HAS_MCP_SDK:
        main_legacy()
        return

    import asyncio
    server = MCPKnwoledgeServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()

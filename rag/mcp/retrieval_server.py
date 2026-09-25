"""
retrieval_server.py — MCP stdio 服务：把 novel-harness 的 RAG 检索能力暴露给 MCP 客户端

工具：
  search_knowledge  — 混合检索（FTS5 + BM25 + 向量），返回可直接注入 Agent 的上下文包
  route_knowledge   — 只做任务路由分析，不检索
  rag_index_stats   — 查看索引统计

与 knowledge_server.py 的分工：
  knowledge_server.py  → 管「知识包」的下载/安装/删除/重建索引
  retrieval_server.py  → 管「知识检索」，给写作/审稿 Agent 当场查规则用

重要：huggingface.co 在部分网络下不可达，sentence-transformers 加载模型时会
反复 HEAD 重试，单次可卡死数分钟。本服务默认设置 HF_HUB_OFFLINE=1 /
TRANSFORMERS_OFFLINE=1，强制走本地缓存（模型缓存缺失时会自动降级为 TF-IDF，
不会阻塞）。如需联网补模型，启动前显式设置 HF_HUB_OFFLINE=0 并配置
HF_ENDPOINT=https://hf-mirror.com。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 必须在 import transformers / sentence_transformers 之前设置
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    # mcp SDK 1.x 里 stdio_server 位于 mcp.server.stdio，
    # 部分旧版本才把它再导出到 mcp.server；两种位置都兼容一下。
    try:
        from mcp.server.stdio import stdio_server
    except ImportError:  # pragma: no cover - 兼容旧版 SDK
        from mcp.server import stdio_server  # type: ignore[attr-defined]

    HAS_MCP_SDK = True
except ImportError:
    HAS_MCP_SDK = False


def _search_knowledge(query: str, task_type: str | None = None, top_k: int = 5,
                      as_text: bool = True) -> dict[str, Any]:
    from rag.src.retriever import hybrid_retrieve
    from rag.src.context_pack import build_context_pack, context_pack_to_text

    result = hybrid_retrieve(query=query, task_type=task_type, top_k=top_k)
    pack = build_context_pack(query=query, retrieval_result=result, task_type=task_type)

    payload: dict[str, Any] = {
        "query": query,
        "task_type": result["meta"]["task_type"],
        "elapsed_ms": result["meta"]["elapsed_ms"],
        "total_candidates": result["meta"]["total_candidates"],
    }
    if as_text:
        payload["context_text"] = context_pack_to_text(pack)
    payload["context_pack"] = pack
    return payload


def _route_knowledge(query: str) -> dict[str, Any]:
    from rag.src.router import route_query
    return route_query(query)


def _index_stats() -> dict[str, Any]:
    import sqlite3
    from rag.src.settings import DB_PATH, VECTORS_DIR

    stats: dict[str, Any] = {
        "db_path": str(DB_PATH),
        "vectors_dir": str(VECTORS_DIR),
        "db_exists": DB_PATH.exists(),
    }
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        try:
            for table in ("documents", "chunks"):
                try:
                    stats[f"{table}_count"] = conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                except sqlite3.Error:
                    pass
        finally:
            conn.close()
    meta = VECTORS_DIR / "meta.pkl"
    stats["vectors_meta_exists"] = meta.exists()
    return stats


# ---------------------------------------------------------------- 工具定义

def _tool_defs() -> list[dict[str, Any]]:
    return [
        {
            "name": "search_knowledge",
            "description": (
                "在 novel-harness 本地知识库中做混合检索（关键词 + 语义 + BM25）。"
                "适用：去 AI 味规则、语病诊断、大纲评估、写前清单、题材边界、节奏检查等。"
                "返回可直接注入 Agent 上下文的文本。"
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "检索问题，用自然语言描述即可"},
                    "task_type": {
                        "type": "string",
                        "description": (
                            "可选，强制指定任务类型；不传则由路由器自动判断。"
                            "取值：humanization / outline_review / chapter_prewrite / "
                            "genre_routing / consistency_check / rhythm_review / ideation"
                        ),
                    },
                    "top_k": {"type": "integer", "default": 5, "description": "返回条数"},
                },
            },
        },
        {
            "name": "route_knowledge",
            "description": "只做任务路由分析：判断一个查询属于哪类写作任务、会去搜哪些分类，不做实际检索。",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
        },
        {
            "name": "rag_index_stats",
            "description": "查看本地 RAG 索引统计（文档数、切段数、向量文件是否存在）。",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "search_knowledge":
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query 不能为空"}
        return _search_knowledge(
            query,
            task_type=(args.get("task_type") or None),
            top_k=int(args.get("top_k") or 5),
        )
    if name == "route_knowledge":
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query 不能为空"}
        return _route_knowledge(query)
    if name == "rag_index_stats":
        return _index_stats()
    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------- MCP SDK 模式

class RetrievalServer:
    def __init__(self) -> None:
        self.server = Server("novel-harness-retrieval")
        self._register()

    def _register(self) -> None:
        srv = self.server
        defs = {d["name"]: d for d in _tool_defs()}

        @srv.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(name=d["name"], description=d["description"], inputSchema=d["inputSchema"])
                for d in defs.values()
            ]

        @srv.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            import asyncio
            if name not in defs:
                raise ValueError(f"Unknown tool: {name}")
            try:
                payload = await asyncio.to_thread(_dispatch, name, arguments or {})
            except Exception as exc:  # noqa: BLE001
                payload = {"error": f"{type(exc).__name__}: {exc}"}
            return [TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            )]

    async def run(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


# ---------------------------------------------------------------- 兼容协议模式（无 mcp SDK 时）

def main_legacy() -> None:
    print("[retrieval_server] mcp SDK 不可用，使用兼容协议模式", file=sys.stderr)
    defs = {d["name"]: d for d in _tool_defs()}

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
        resp: dict[str, Any] | None

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "novel-harness-retrieval", "version": "1.0.0"},
                },
            }
        elif method == "notifications/initialized":
            resp = None
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {}}
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0", "id": rid,
                "result": {"tools": [{"name": n, **d} for n, d in defs.items()]},
            }
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            if name not in defs:
                resp = {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
            else:
                try:
                    payload = _dispatch(name, params.get("arguments") or {})
                    is_error = "error" in payload
                except Exception as exc:  # noqa: BLE001
                    payload = {"error": f"{type(exc).__name__}: {exc}"}
                    is_error = True
                resp = {
                    "jsonrpc": "2.0", "id": rid,
                    "result": {
                        "content": [{"type": "text",
                                     "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                        "isError": is_error,
                    },
                }
        else:
            resp = {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}

        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)


def _warmup() -> None:
    """在进入事件循环之前，把重型导入和模型加载全部做完。

    原因：RAG 检索的第一次调用会 import torch / sentence-transformers，
    在工作线程（asyncio.to_thread）里首次 import 这些库，在 Windows 上会死锁，
    表现是 MCP 工具调用永远不返回。放到主线程预热即可规避。
    """
    if os.environ.get("NOVEL_HARNESS_SKIP_WARMUP") == "1":
        return
    try:
        from rag.src import retriever, router, context_pack  # noqa: F401
        from rag.src.embedder import _try_load_transformer
        _try_load_transformer()
        # 再跑一次最小检索，把 TF-IDF/BM25 词表和向量存储的首次构建也放在主线程完成
        try:
            _search_knowledge("预热", top_k=1, as_text=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[retrieval_server] warmup 检索跳过: {type(exc).__name__}: {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[retrieval_server] warmup 警告: {type(exc).__name__}: {exc}", file=sys.stderr)


def main() -> None:
    _warmup()
    if not HAS_MCP_SDK:
        main_legacy()
        return
    import asyncio
    asyncio.run(RetrievalServer().run())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ragctl — novel-harness RAG 命令行工具

用法:
    ragctl build-index        重建 RAG 索引
    ragctl server             启动 HTTP 服务 (localhost:3456)
    ragctl query <text>       检索查询
    ragctl route <text>       查看路由分析
    ragctl stats              查看索引统计
    ragctl health             健康检查
    ragctl list-packs         列出知识包
    ragctl install-pack <id>  安装知识包
"""

import sys
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def cmd_build_index(args):
    from rag.src.indexer import build_full_index
    stats = build_full_index()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_server(args):
    from rag.src.server import app
    import uvicorn
    host = args.host or "0.0.0.0"
    port = args.port or 3456
    uvicorn.run(app, host=host, port=port)


def cmd_query(args):
    from rag.src.retriever import hybrid_retrieve
    from rag.src.context_pack import build_context_pack, context_pack_to_text

    result = hybrid_retrieve(
        query=args.query,
        task_type=args.task_type,
        top_k=args.top_k,
    )
    context_pack = build_context_pack(
        query=args.query,
        retrieval_result=result,
        task_type=args.task_type,
    )
    if args.json:
        print(json.dumps(context_pack, ensure_ascii=False, indent=2))
    else:
        print(context_pack_to_text(context_pack))
        meta = result["meta"]
        print(f"\n[元信息] 耗时: {meta['elapsed_ms']}ms, "
              f"候选: {meta['total_candidates']}, "
              f"任务类型: {meta['task_type']}")


def cmd_route(args):
    from rag.src.router import route_query
    route = route_query(args.query)
    print(json.dumps(route, ensure_ascii=False, indent=2))


def cmd_stats(args):
    from rag.src.storage import sqlite_store, vector_store
    sqlite_stats = sqlite_store.get_stats()
    vec_count = vector_store.get_vector_count()
    print(json.dumps({
        "sqlite": sqlite_stats,
        "vectors": vec_count,
    }, ensure_ascii=False, indent=2))


def cmd_health(args):
    from datetime import datetime
    from rag.src.storage import sqlite_store, vector_store
    stats = sqlite_store.get_stats()
    vec_count = vector_store.get_vector_count()
    print(json.dumps({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "sqlite_has_data": stats["documents"] > 0,
        "vectors_loaded": vec_count > 0,
    }, ensure_ascii=False, indent=2))


def cmd_list_packs(args):
    from rag.scripts.sync_packs import list_packs as _list_packs
    argv = ["list"]
    if args.include_remote:
        argv.append("--include-remote")
    if args.json:
        argv.append("--json")
    if args.pack_type:
        argv.extend(["--type", args.pack_type])

    class FakeArgs:
        manifest = args.manifest
        include_remote = args.include_remote
        pack_type = args.pack_type
        json = args.json

    _list_packs(FakeArgs())


def cmd_install_pack(args):
    from rag.scripts.sync_packs import install_pack as _install
    class FakeArgs:
        manifest = args.manifest
        pack_id = args.pack_id
        pack_type = None
        rebuild_index = args.rebuild_index
    _install(FakeArgs())


def main():
    parser = argparse.ArgumentParser(
        description="novel-harness RAG 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="更多信息: https://github.com/anomalyco/novel-harness",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # build-index
    sub.add_parser("build-index", help="重建 RAG 索引")

    # server
    svr = sub.add_parser("server", help="启动 RAG HTTP 服务")
    svr.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    svr.add_argument("--port", type=int, default=3456, help="监听端口 (默认 3456)")

    # query
    q = sub.add_parser("query", help="检索查询")
    q.add_argument("query", help="检索文本")
    q.add_argument("--task-type", help="任务类型过滤")
    q.add_argument("--top-k", type=int, default=5)
    q.add_argument("--json", action="store_true")

    # route
    r = sub.add_parser("route", help="路由分析")
    r.add_argument("query", help="查询文本")

    # stats
    sub.add_parser("stats", help="索引统计")

    # health
    sub.add_parser("health", help="健康检查")

    # list-packs
    lp = sub.add_parser("list-packs", help="列出知识包")
    lp.add_argument("--include-remote", action="store_true")
    lp.add_argument("--pack-type", help="按类型过滤")
    lp.add_argument("--manifest", help="远程 manifest URL")
    lp.add_argument("--json", action="store_true")

    # install-pack
    ip = sub.add_parser("install-pack", help="安装知识包")
    ip.add_argument("pack_id", help="知识包 ID")
    ip.add_argument("--manifest", help="远程 manifest URL")
    ip.add_argument("--rebuild-index", action="store_true")

    args = parser.parse_args()

    handlers = {
        "build-index": cmd_build_index,
        "server": cmd_server,
        "query": cmd_query,
        "route": cmd_route,
        "stats": cmd_stats,
        "health": cmd_health,
        "list-packs": cmd_list_packs,
        "install-pack": cmd_install_pack,
    }

    handlers[args.command](args)


if __name__ == "__main__":
    main()

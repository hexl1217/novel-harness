#!/usr/bin/env python3
"""
benchmark.py — RAG 检索基准测试

测量：
  - 单次检索延迟 (FTS / BM25 / 向量 / 混合)
  - Recall@k 对已知查询
  - 吞吐量 (RPS)
  - 向量库统计

用法：
    python rag/test/benchmark.py                     # 快速运行 (5 轮预热)
    python rag/test/benchmark.py --warmup 10 --runs 50
    python rag/test/benchmark.py --json              # JSON 输出
"""

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.src import bm25_retriever
from rag.src.embedder import embed_text
from rag.src.retriever import hybrid_retrieve
from rag.src.router import route_query
from rag.src.storage import sqlite_store, vector_store


BENCHMARK_QUERIES = [
    ("去AI味修改", "humanization", ["去AI味最小修改指南"]),
    ("大纲质量评估", "outline_review", ["大纲质量评估清单"]),
    ("写作前准备清单", "chapter_prewrite", ["章节写前准备清单"]),
    ("全民求生题材", "genre_routing", ["全民求生"]),
    ("节奏太平", "rhythm_review", ["阅读体验"]),
    ("角色状态矛盾", "consistency_check", ["角色关系"]),
    ("剧情灵感", "ideation", ["灵感"]),
    ("AI 味太重", "humanization", ["去AI味"]),
    ("检查大纲结构", "outline_review", ["大纲"]),
    ("这章读起来很拖", "rhythm_review", ["节奏"]),
]


KB = 1024
MB = 1024 * KB


def format_bytes(n: int) -> str:
    if n >= MB:
        return f"{n / MB:.1f} MB"
    if n >= KB:
        f"{n / KB:.1f} KB"
    return f"{n} B"


def measure_latency(fn, kwargs, runs: int = 20, warmup: int = 5) -> dict:
    for _ in range(warmup):
        fn(**kwargs)

    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn(**kwargs)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    times.sort()
    n = len(times)
    return {
        "min_ms": round(times[0], 2),
        "max_ms": round(times[-1], 2),
        "avg_ms": round(sum(times) / n, 2),
        "p50_ms": round(times[n // 2], 2),
        "p95_ms": round(times[int(n * 0.95)], 2),
        "p99_ms": round(times[int(n * 0.99)], 2),
    }


def benchmark_all(runs: int = 20, warmup: int = 5, json_output: bool = False):
    results = {
        "metadata": {
            "vector_count": vector_store.get_vector_count(),
            "sqlite_stats": sqlite_store.get_stats(),
            "benchmark_queries": len(BENCHMARK_QUERIES),
            "runs_per_query": runs,
        },
        "latency": {},
        "recall": {},
    }

    results["latency"]["hybrid_retrieve"] = measure_latency(
        hybrid_retrieve, {"query": "去AI味修改", "task_type": "humanization", "top_k": 5},
        runs=runs, warmup=warmup,
    )

    if bm25_retriever._built:
        results["latency"]["bm25_search"] = measure_latency(
            lambda: bm25_retriever.bm25_search("去AI味修改", 15), {}, runs=runs, warmup=warmup,
        )

    recall_results = {"hits": 0, "total": 0, "details": []}
    for query, task_type, expected_titles in BENCHMARK_QUERIES:
        result = hybrid_retrieve(query=query, task_type=task_type, top_k=5)
        top_titles = [r["title"] for r in result["results"]]

        hit = any(any(exp in t for exp in expected_titles) for t in top_titles)
        recall_results["hits"] += 1 if hit else 0
        recall_results["total"] += 1
        recall_results["details"].append({
            "query": query,
            "task_type": task_type,
            "hit": hit,
            "top1": top_titles[0] if top_titles else None,
            "top5": top_titles,
            "expected": expected_titles,
        })

    results["recall"]["hybrid@5"] = {
        "hit_count": recall_results["hits"],
        "total": recall_results["total"],
        "recall": round(recall_results["hits"] / recall_results["total"], 3),
        "details": recall_results["details"] if json_output else None,
    }

    if json_output:
        # JSON 模式：全量
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        # 表格模式
        meta = results["metadata"]
        print(f"\n{'=' * 52}")
        print(f"  RAG 基准测试")
        print(f"{'=' * 52}")
        print(f"  向量数:     {meta['vector_count']}")
        print(f"  SQLite文档: {meta['sqlite_stats']['documents']}")
        print(f"  SQLite块:   {meta['sqlite_stats']['chunks']}")
        print(f"  测试查询:   {meta['benchmark_queries']}")
        print(f"  每轮运行:   {meta['runs_per_query']}")
        print(f"{'=' * 52}")

        for name, lat in results["latency"].items():
            print(f"\n  [{name}]")
            print(f"    平均: {lat['avg_ms']:>7.1f} ms")
            print(f"    P50:  {lat['p50_ms']:>7.1f} ms")
            print(f"    P95:  {lat['p95_ms']:>7.1f} ms")
            print(f"    P99:  {lat['p99_ms']:>7.1f} ms")
            print(f"    范围: {lat['min_ms']:>7.1f} ~ {lat['max_ms']:.1f} ms")

        recall = results["recall"]["hybrid@5"]
        print(f"\n  [Recall@5]")
        print(f"    命中: {recall['hit_count']}/{recall['total']} ({recall['recall']:.1%})")

        for d in recall["details"]:
            marker = "✓" if d["hit"] else "✗"
            print(f"    {marker} {d['query']:20s} → top1={str(d['top1'])[:30]}")

        print(f"\n{'=' * 52}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RAG 检索基准测试")
    parser.add_argument("--runs", type=int, default=20, help="每查询运行次数")
    parser.add_argument("--warmup", type=int, default=5, help="预热次数")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    benchmark_all(runs=args.runs, warmup=args.warmup, json_output=args.json)

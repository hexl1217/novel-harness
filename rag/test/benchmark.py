#!/usr/bin/env python3
"""
benchmark.py — RAG 检索基准测试

测量：
  - 单次检索延迟 (FTS / BM25 / 向量 / 混合)
  - Recall@k 对已知查询
  - 吞吐量 (RPS)
  - 向量库统计

用法：
    python rag/test/benchmark.py                       # 快速运行
    python rag/test/benchmark.py --warmup 10 --runs 50
    python rag/test/benchmark.py --json                # JSON 输出
    python rag/test/benchmark.py --save-baseline rag/test/baseline.json
    python rag/test/benchmark.py --check rag/test/baseline.json   # CI 用

--check 会对比基线并在退化时以退出码 1 结束：
  * Recall@5 低于基线
  * 任一基线中「命中」的查询退化为「未命中」
  * P95 延迟超过基线 × --latency-factor（默认 3.0，CI 机器波动大）

没有这层基线，任何检索侧改动都无法判断是变好还是变坏——
此前修 BM25 / FTS / 分词时就只能靠单个 query 的分数当证据。
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.src import bm25_retriever
from rag.src.retriever import hybrid_retrieve
from rag.src.storage import sqlite_store, vector_store


BENCHMARK_QUERIES = [
    ("去AI味修改", "humanization", ["去AI味最小修改指南"]),
    ("大纲质量评估", "outline_review", ["大纲质量评估清单"]),
    ("写作前准备清单", "chapter_prewrite", ["章节写前准备清单"]),
    ("全民求生题材", "genre_routing", ["全民求生"]),
    ("节奏太平", "rhythm_review", ["节奏"]),
    ("角色状态矛盾", "consistency_check", ["角色状态", "矛盾"]),
    ("剧情灵感", "ideation", ["灵感"]),
    ("AI 味太重", "humanization", ["去AI味"]),
    ("检查大纲结构", "outline_review", ["大纲"]),
    ("这章读起来很拖", "rhythm_review", ["阅读体验"]),
]


KB = 1024
MB = 1024 * KB


def format_bytes(n: int) -> str:
    if n >= MB:
        return f"{n / MB:.1f} MB"
    if n >= KB:
        return f"{n / KB:.1f} KB"
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


def benchmark_all(runs: int = 20, warmup: int = 5, json_output: bool = False) -> dict:
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

    # details 必须始终保留：表格模式也要遍历它，
    # 之前写成 `if json_output else None` 会让默认运行直接 TypeError。
    results["recall"]["hybrid@5"] = {
        "hit_count": recall_results["hits"],
        "total": recall_results["total"],
        "recall": round(recall_results["hits"] / recall_results["total"], 3),
        "details": recall_results["details"],
    }

    if json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
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

    return results


def to_baseline(results: dict) -> dict:
    """把一次运行结果压成基线文件（只留可比较的判据）。"""
    recall = results["recall"]["hybrid@5"]
    stats = results["metadata"]["sqlite_stats"]
    latency = results["latency"]["hybrid_retrieve"]
    return {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": {
            "documents": stats["documents"],
            "chunks": stats["chunks"],
            "vectors": results["metadata"]["vector_count"],
        },
        "recall_at_5": recall["recall"],
        "hit_count": recall["hit_count"],
        "total": recall["total"],
        "per_query": {d["query"]: d["hit"] for d in recall["details"]},
        "latency_avg_ms": latency["avg_ms"],
        "latency_p95_ms": latency["p95_ms"],
    }


def save_baseline(results: dict, path: str) -> None:
    baseline = to_baseline(results)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def check_baseline(results: dict, path: str, latency_factor: float = 3.0):
    """对比基线。返回 (是否通过, 消息列表)。"""
    target = Path(path)
    if not target.exists():
        return False, [f"基线文件不存在: {path}"]

    base = json.loads(target.read_text(encoding="utf-8"))
    messages = []
    ok = True

    # 1. 语料规模：变了就说明基线不可比（知识包已改动）
    base_corpus = base.get("corpus", {})
    cur_stats = results["metadata"]["sqlite_stats"]
    if base_corpus.get("chunks") and cur_stats["chunks"] != base_corpus["chunks"]:
        messages.append(
            f"[!] 语料规模已变化: chunks {base_corpus['chunks']} → {cur_stats['chunks']}"
            f"（基线记录于 {base.get('recorded_at', '?')}，可比性下降，建议重新生成基线）"
        )

    # 2. 总 Recall@5 不得下降
    recall = results["recall"]["hybrid@5"]
    cur = recall["recall"]
    if cur < base["recall_at_5"]:
        ok = False
        messages.append(f"[FAIL] Recall@5 下降: {base['recall_at_5']:.3f} → {cur:.3f}")
    else:
        messages.append(f"[OK] Recall@5 {cur:.3f} ≥ 基线 {base['recall_at_5']:.3f}")

    # 3. 逐查询：基线命中的不允许退化为未命中（能定位到具体 regressed query）
    cur_detail = {d["query"]: d["hit"] for d in recall["details"]}
    regressed = [
        q for q, hit in base.get("per_query", {}).items()
        if hit and not cur_detail.get(q, False)
    ]
    if regressed:
        ok = False
        messages.append(f"[FAIL] 以下查询由「命中」退化为「未命中」: {regressed}")
    else:
        messages.append("[OK] 无逐查询退化")

    # 4. P95 延迟上界
    p95 = results["latency"]["hybrid_retrieve"]["p95_ms"]
    limit = base.get("latency_p95_ms", 0) * latency_factor
    if limit and p95 > limit:
        ok = False
        messages.append(
            f"[FAIL] P95 延迟超上界: {p95:.1f}ms > {limit:.1f}ms"
            f"（基线 {base['latency_p95_ms']:.1f}ms × {latency_factor}）"
        )
    else:
        messages.append(f"[OK] P95 延迟 {p95:.1f}ms ≤ 上界 {limit:.1f}ms（放宽 {latency_factor}×）")

    return ok, messages


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RAG 检索基准测试")
    parser.add_argument("--runs", type=int, default=20, help="每查询运行次数")
    parser.add_argument("--warmup", type=int, default=5, help="预热次数")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--save-baseline", metavar="PATH", help="把本次结果记录为基线文件")
    parser.add_argument("--check", metavar="PATH", help="对比基线，退化时退出码 1")
    parser.add_argument(
        "--latency-factor", type=float, default=3.0,
        help="延迟放宽倍数（默认 3.0；CI 机器波动大，不宜精确比对）",
    )
    args = parser.parse_args(argv)

    results = benchmark_all(runs=args.runs, warmup=args.warmup, json_output=args.json)

    code = 0

    if args.save_baseline:
        save_baseline(results, args.save_baseline)
        print(f"\n基线已保存: {args.save_baseline}")

    if args.check:
        ok, messages = check_baseline(results, args.check, args.latency_factor)
        print(f"\n{'=' * 52}")
        print(f"  基线对比: {args.check}")
        print(f"{'=' * 52}")
        for m in messages:
            print(f"  {m}")
        print(f"{'=' * 52}")
        code = 0 if ok else 1

    return code


if __name__ == "__main__":
    sys.exit(main())

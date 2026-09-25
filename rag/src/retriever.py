"""
retriever.py - 混合检索器。

组合 FTS5 + BM25 + 向量检索，按加权公式打分，输出最终 top-k chunks。

**关于重排（2026-09-26 重做）**

本模块原先调用 ``reranker.rerank(..., top_n=2*top_k)``。该函数有两条路径：
CrossEncoder（英文 STS 模型 ``cross-encoder/stsb-distilroberta-base``）与「词重叠」
降级路径。受控实验（同索引、同查询集，唯一变量是模型是否加载）后的结论是
**只删 CrossEncoder，保留词重叠初筛**（见 `_screen_by_query_overlap`）：

    CrossEncoder 生效    Recall@5 = 0.700    单次检索 ~8.4 s
    词重叠初筛          Recall@5 = 1.000    单次检索 ~82 ms

删 CrossEncoder 的三条独立理由：

1. 它是**英文 STS 模型**，给中文 query/段落对打分；
2. 它把 47~62 个候选**截断**到 ``top_n``，而这个 top_n 只有 ``2*top_k``；
3. 截断之后又按 ``score`` 排了一次，而它只写 ``ce_score`` ——
   **模型给出的顺序被整条丢弃，它实际只充当了「截断器」**。

第 3 点意味着「修排序」救不了它：让模型排序真正生效只会更差（0.700 就是它的成绩）。

而「词重叠」那条路径**不能陪着一起删**。它名义上是降级分支，实际承担着初筛职责：
单独去掉它，Recall@5 会从 1.000 掉到 0.900（query「大纲质量评估」的正确答案落到
第 6 名，与第 5 名只差 0.0036）。所以它被提升为唯一实现，并移入本模块。

若将来要重新引入模型精排，必须**同时**满足两条，缺一不可：

- 换成中文 reranker（如 ``BAAI/bge-reranker-base``）；
- 让最终排序真正使用重排分数（``sort(key=重排分)``），而不是当作截断器。
"""

from .logger import get_logger
from . import bm25_retriever
from . import router as router_mod
from .embedder import embed_text
from .storage import sqlite_store, vector_store

logger = get_logger("retriever")

SOURCE_WEIGHTS = {"rule": 1.0, "knowledge": 0.9, "reference": 0.8, "project": 0.6}
_BM25_WEIGHT = 0.25
_FTS_WEIGHT = 0.20
_VEC_WEIGHT = 0.30
_TASK_WEIGHT = 0.25


def hybrid_retrieve(query, task_type=None, top_k=5, fts_n=30, vec_n=30, bm25_n=30):
    import time
    start_time = time.time()
    query_lower = query.lower()

    if task_type:
        route_result = {"task_type": task_type, **router_mod.get_route(task_type)}
    else:
        route_result = router_mod.route_query(query)
    task_route = route_result

    fts_results = _retrieve_fts(query, task_route, fts_n)
    # BM25 索引只在进程内存在，索引构建脚本之外没人建过它 ——
    # 这里懒加载，否则 bm25_search 恒返回空（整条通道静默失效）。
    #
    # 历史 bug：这两行曾写在 `if use_rerank:` 里，于是「关掉重排」会连带静默
    # 关掉整条 BM25 召回 —— 当时那条 `use_rerank=False` 的用例，实际测的是
    # 「关掉 BM25」而不是「不许重排」。BM25 与重排无关，必须无条件执行。
    bm25_retriever.ensure_index()
    bm25_results = bm25_retriever.bm25_search(query, bm25_n)
    vec_results = _retrieve_vector(query, vec_n)

    merged = _merge_results(fts_results, bm25_results, vec_results, query_lower, task_route)
    merged = _screen_by_query_overlap(merged, query_lower, top_n=top_k * 2)
    merged.sort(key=lambda x: x["score"], reverse=True)
    final = merged[:top_k]

    final_results = []
    for r in final:
        text = r.get("text", "") or r.get("snippet", "") or ""
        final_results.append({
            "chunk_id": r["chunk_id"],
            "title": r.get("title", ""),
            "score": r.get("score", 0),
            "reason": _build_reason(r),
            "snippet": text[:200] + ("..." if len(text) > 200 else ""),
            "source_path": r.get("source_path", ""),
            "source_type": r.get("source_type", ""),
            "category": r.get("category", ""),
            "tags": r.get("tags", []),
            "priority": r.get("priority", 3),
        })

    elapsed = time.time() - start_time
    return {
        "results": final_results,
        "meta": {
            "total_candidates": len(merged),
            "fts_count": len(fts_results),
            "bm25_count": len(bm25_results),
            "vector_count": len(vec_results),
            "elapsed_ms": round(elapsed * 1000),
            "task_type": route_result.get("task_type"),
            "confidence": route_result.get("confidence", 0),
        },
    }


def _retrieve_fts(query, task_route, fts_n):
    """全文检索通道。

    全文检索优先走 ``fts_search``：它使用 FTS5 + 与写入端一致的 CJK 预分词，
    是唯一能做子串级中文匹配的通道。

    历史实现用 ``filter_chunks`` **替代**了全文检索：只要任务路由配了
    categories，返回的就是「ORDER BY priority 的前 N 个同类 chunk」，与 query
    完全无关；又因为中文查询经 ``split()`` 后只剩一个整词、子串匹配必然失败，
    所有候选还被统一赋 -0.1 的兜底分。双重失效——函数名叫 fts，实际没做检索。

    现在全文检索是主路径，类别候选降为**兜底**（仅当全文检索无结果时使用，
    例如查询全是停用词），保证任务域内仍有可用上下文。任务先验本就由
    ``_compute_task_match`` 统一承担，不该在这里重复，更不该污染相关性分。
    """
    results = sqlite_store.fts_search(query, fts_n)
    if results:
        return results

    categories = (task_route or {}).get("categories", [])
    stages = (task_route or {}).get("stages", [])
    if categories or stages:
        return sqlite_store.filter_chunks(
            categories=categories, stages=stages, top_n=fts_n
        )
    return results


def _retrieve_vector(query, vec_n):
    try:
        query_vector = embed_text(query)
        return vector_store.vector_search(query_vector, vec_n)
    except Exception as exc:
        logger.error("向量检索失败: %s", exc)
        return []


def _merge_results(fts_results, bm25_results, vec_results, query_lower, task_route):
    candidates = {}

    for r in fts_results:
        cid = r["chunk_id"]
        candidates[cid] = {
            "chunk_id": cid,
            "title": r.get("title", ""),
            "text": r.get("text", ""),
            "fts_score": r.get("fts_score", 0),
            "bm25_score": None,
            "vec_score": None,
            "source_path": r.get("source_path", ""),
            "source_type": r.get("source_type", ""),
            "category": r.get("category", ""),
            "tags": r.get("tags", []),
            "priority": r.get("priority", 3),
        }

    for r in bm25_results:
        cid = r["chunk_id"]
        if cid in candidates:
            candidates[cid]["bm25_score"] = r["score"]
        else:
            candidates[cid] = {
                "chunk_id": cid,
                "title": r.get("title", ""),
                "text": r.get("text", ""),
                "fts_score": None,
                "bm25_score": r["score"],
                "vec_score": None,
                "source_path": r.get("source_path", ""),
                "source_type": r.get("source_type", ""),
                "category": r.get("category", ""),
                "tags": r.get("tags", []),
                "priority": r.get("priority", 3),
            }

    vec_map = {r["chunk_id"]: r["score"] for r in vec_results}
    for cid, score in vec_map.items():
        if cid in candidates:
            candidates[cid]["vec_score"] = score
        else:
            chunk_data = sqlite_store.get_chunk_by_id(cid)
            if chunk_data:
                candidates[cid] = {
                    "chunk_id": cid,
                    "title": chunk_data.get("title", ""),
                    "text": chunk_data.get("text", ""),
                    "fts_score": None,
                    "bm25_score": None,
                    "vec_score": score,
                    "source_path": chunk_data.get("source_path", ""),
                    "source_type": chunk_data.get("source_type", ""),
                    "category": chunk_data.get("category", ""),
                    "tags": chunk_data.get("tags", []),
                    "priority": chunk_data.get("priority", 3),
                }

    for cid, cand in candidates.items():
        cand["score"] = _compute_score(cand, query_lower, task_route)

    return list(candidates.values())


def _screen_by_query_overlap(candidates, query_lower, top_n):
    """初筛：用「原分数 + 查询词重叠」挑出最靠前的 top_n 个候选。

    这一步**不是精排** —— 最终顺序仍由 ``score`` 决定（调用方接着
    ``sort(key=score)`` 再取前 k）。它的作用是保证「标题/正文真正含查询词」
    的候选不会被纯语义分挤到后面。

    为什么需要它：中文查询经 ``str.split()`` 通常只得到一个整词
    （如「大纲质量评估」），于是 ``t in text`` 退化为**子串匹配** ——
    「这段就是讲这个的」的强信号。它零依赖、不加载任何模型。

    2026-09-26 实测（query「大纲质量评估」，索引 983 文档 / 8750 chunks）：
    去掉这一步后正确答案落到第 6 名（score 0.8002，与第 5 名 0.8038 只差
    0.0036），该查询未命中，Recall@5 由 1.000 降到 0.900；保留则回到 1.000。

    历史背景：这一逻辑原先藏在 ``reranker._rerank_score_based`` 里，作为
    CrossEncoder 不可用时的「降级路径」。同期核查发现 CrossEncoder
    （英文 STS 模型 ``stsb-distilroberta-base``）才是真正有害的那半 ——
    它使 Recall@5 掉到 0.700。所以移除的是 CrossEncoder，保留的是这里。
    """
    if len(candidates) <= 1:
        return candidates

    query_terms = set(query_lower.split())
    for c in candidates:
        text = ((c.get("text", "") or "") + " " + (c.get("title", "") or "")).lower()
        overlap = sum(1 for t in query_terms if t in text) / max(len(query_terms), 1)
        base = c.get("score", 0)
        if not isinstance(base, (int, float)):
            base = 0.0
        c["overlap_score"] = base * 0.7 + overlap * 0.3

    ranked = sorted(candidates, key=lambda x: x.get("overlap_score", 0), reverse=True)
    return ranked[:top_n]


def _compute_score(cand, query_lower, task_route):
    fts = cand.get("fts_score")
    bm25 = cand.get("bm25_score")
    vec = cand.get("vec_score")

    fts_norm = 0.0
    if isinstance(fts, (int, float)) and fts is not None and fts < 0:
        fts_norm = min(1.0, max(0.0, -fts / 30))

    bm25_norm = 0.0
    if isinstance(bm25, (int, float)) and bm25 is not None and bm25 > 0:
        bm25_norm = min(1.0, bm25 / 15)

    vec_norm = 0.0
    if isinstance(vec, (int, float)) and vec is not None:
        vec_norm = min(1.0, max(0.0, vec))

    task_match = _compute_task_match(cand, task_route, query_lower)
    priority_weight = (6 - (cand.get("priority", 3) or 3)) / 5
    source_weight = SOURCE_WEIGHTS.get(cand.get("source_type"), 0.5)

    return round(
        vec_norm * _VEC_WEIGHT
        + fts_norm * _FTS_WEIGHT
        + bm25_norm * _BM25_WEIGHT
        + task_match * _TASK_WEIGHT
        + priority_weight * 0.08
        + source_weight * 0.04,
        4,
    )


def _compute_task_match(cand, task_route, query_lower):
    if not task_route:
        return 0.0
    match = 0.0
    categories = task_route.get("categories", [])
    if categories and cand.get("category") in categories:
        match += 0.5
    stages = task_route.get("stages", [])
    if cand.get("stage") and any(stage in str(cand["stage"]) for stage in stages):
        match += 0.3
    return min(1.0, match)


def _build_reason(cand):
    parts = []
    fts = cand.get("fts_score")
    bm25 = cand.get("bm25_score")
    vec = cand.get("vec_score")

    if isinstance(fts, (int, float)) and fts is not None and fts < 0:
        parts.append("关键词匹配")
    if isinstance(bm25, (int, float)) and bm25 is not None and bm25 > 0:
        parts.append("BM25 稀疏检索")
    if isinstance(vec, (int, float)) and vec is not None and vec > 0.3:
        parts.append("语义接近")
    if cand.get("category"):
        parts.append(f"类型:{cand['category']}")
    if cand.get("source_type") == "rule":
        parts.append("规则文档")
    if cand.get("source_type") == "knowledge":
        parts.append("知识包")
    if cand.get("priority", 3) <= 2:
        parts.append("高优先级")
    if not parts:
        parts.append("综合匹配")
    return " + ".join(parts)

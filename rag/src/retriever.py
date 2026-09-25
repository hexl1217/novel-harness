"""
retriever.py - 混合检索器。

组合 FTS5 + BM25 + 向量检索 + CrossEncoder 重排，
输出最终 top-k chunks。
"""

from .logger import get_logger
from . import bm25_retriever
from . import reranker as reranker_mod
from . import router as router_mod
from .embedder import embed_text
from .storage import sqlite_store, vector_store

logger = get_logger("retriever")

SOURCE_WEIGHTS = {"rule": 1.0, "knowledge": 0.9, "reference": 0.8, "project": 0.6}
_BM25_WEIGHT = 0.25
_FTS_WEIGHT = 0.20
_VEC_WEIGHT = 0.30
_TASK_WEIGHT = 0.25


def hybrid_retrieve(query, task_type=None, top_k=5, fts_n=30, vec_n=30, bm25_n=30, use_rerank=True):
    import time
    start_time = time.time()
    query_lower = query.lower()

    if task_type:
        route_result = {"task_type": task_type, **router_mod.get_route(task_type)}
    else:
        route_result = router_mod.route_query(query)
    task_route = route_result

    fts_results = _retrieve_fts(query, task_route, fts_n)
    bm25_results = bm25_retriever.bm25_search(query, bm25_n) if use_rerank else []
    vec_results = _retrieve_vector(query, vec_n)

    merged = _merge_results(fts_results, bm25_results, vec_results, query_lower, task_route)

    reranked = merged
    if use_rerank and len(merged) > 1:
        reranked = reranker_mod.rerank(query, merged, top_n=top_k * 2)

    reranked.sort(key=lambda x: x["score"], reverse=True)
    final = reranked[:top_k]

    final_results = []
    for r in final:
        text = r.get("text", "") or r.get("snippet", "") or ""
        final_results.append({
            "chunk_id": r["chunk_id"],
            "title": r.get("title", ""),
            "score": r.get("score", 0),
            "ce_score": r.get("ce_score"),
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
            "rerank_used": use_rerank and len(merged) > 1,
        },
    }


def _retrieve_fts(query, task_route, fts_n):
    fts_results = []
    categories = task_route.get("categories", [])
    stages = task_route.get("stages", [])

    if categories:
        filtered = sqlite_store.filter_chunks(categories=categories, stages=stages, top_n=fts_n)
        for row in filtered:
            text = (row.get("title", "") + " " + row.get("text", "")).lower()
            terms = [t for t in query.lower().split() if t]
            score = 0
            for term in terms:
                if term in text:
                    score -= 1
            if row.get("title", "").lower() and any(term in row["title"].lower() for term in terms):
                score -= 3
            row["fts_score"] = score if score < 0 else -0.1
            fts_results.append(row)
        fts_results = [r for r in fts_results if r.get("fts_score", 0) < 0]

    if not fts_results:
        fts_results = sqlite_store.fts_search(query, fts_n)
        for r in fts_results:
            r["fts_score"] = r.get("fts_score", 0)
    return fts_results


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
    if cand.get("ce_score") is not None:
        parts.append("CrossEncoder 重排")
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

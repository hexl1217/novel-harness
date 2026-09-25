"""
reranker.py — CrossEncoder 重排序器

使用 sentence-transformers 的 CrossEncoder 对检索结果做精排。
自动降级到基于分数的简单重排（CrossEncoder 不可用时）。
"""

import threading
from typing import Any

from .logger import get_logger

logger = get_logger("reranker")

_cross_encoder = None
_model_attempted = False
_lock = threading.Lock()


def _try_load_model():
    global _cross_encoder, _model_attempted
    if _model_attempted:
        return
    with _lock:
        if _model_attempted:
            return
        _model_attempted = True
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder("cross-encoder/stsb-distilroberta-base")
            logger.info("CrossEncoder 模型加载成功")
        except Exception as e:
            logger.warning("CrossEncoder 加载失败: %s，将使用基于分数的重排", e)


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    _try_load_model()

    if _cross_encoder is not None:
        return _rerank_cross_encoder(query, candidates, top_n)
    return _rerank_score_based(query, candidates, top_n)


def _rerank_cross_encoder(
    query: str,
    candidates: list[dict[str, Any]],
    top_n: int | None,
) -> list[dict[str, Any]]:
    pairs = [(query, c.get("text", "") or c.get("snippet", "") or "") for c in candidates]
    try:
        scores = _cross_encoder.predict(pairs, show_progress_bar=False)
    except Exception as e:
        logger.warning("CrossEncoder 预测失败: %s，降级到基于分数的重排", e)
        return _rerank_score_based(query, candidates, top_n)

    for i, candidate in enumerate(candidates):
        candidate["ce_score"] = float(scores[i])

    reranked = sorted(candidates, key=lambda x: x.get("ce_score", 0), reverse=True)

    if top_n is not None and top_n < len(reranked):
        reranked = reranked[:top_n]

    return reranked


def _rerank_score_based(
    query: str,
    candidates: list[dict[str, Any]],
    top_n: int | None,
) -> list[dict[str, Any]]:
    query_lower = query.lower()
    query_terms = set(query_lower.split())

    for c in candidates:
        text = (c.get("text", "") + " " + c.get("title", "")).lower()
        term_overlap = sum(1 for t in query_terms if t in text) / max(len(query_terms), 1)

        base_score = c.get("score", 0) or c.get("fts_score", 0) or 0
        if isinstance(base_score, (int, float)):
            c["ce_score"] = base_score * 0.7 + term_overlap * 0.3
        else:
            c["ce_score"] = term_overlap

    reranked = sorted(candidates, key=lambda x: x.get("ce_score", 0), reverse=True)

    if top_n is not None and top_n < len(reranked):
        reranked = reranked[:top_n]

    return reranked

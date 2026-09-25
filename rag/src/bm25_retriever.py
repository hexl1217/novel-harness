"""
bm25_retriever.py — BM25 稀疏检索器

使用 rank_bm25 库实现 Okapi BM25 算法，作为 FTS5 的替代/补充。
对中文文本做智能分词后索引。
"""

import math
import re
import threading
from pathlib import Path

import numpy as np

from .logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

logger = get_logger("bm25_retriever")

_bm25 = None
_corpus: list[dict] = []
_tokenized: list[list[str]] = []
_built = False
_lock = threading.Lock()

_STOP_WORDS = frozenset({
    "的", "了", "是", "在", "有", "和", "就", "不", "都", "而",
    "且", "但", "也", "之", "与", "这", "那", "到", "去", "能",
    "会", "可", "以", "让", "把", "被", "从", "对", "为", "上",
    "下", "中", "里", "着", "过", "没", "很", "太", "更", "最",
    "又", "再", "才", "还", "已", "将", "要", "所", "如", "于",
    "其", "各", "因", "或", "及", "等",
})


def tokenize(text: str) -> list[str]:
    text = str(text).lower()
    tokens = []
    i = 0
    while i < len(text):
        ch = text[i]
        if "\u4e00" <= ch <= "\u9fff":
            if ch not in _STOP_WORDS:
                tokens.append(ch)
                if i + 1 < len(text) and "\u4e00" <= text[i + 1] <= "\u9fff":
                    bigram = text[i:i + 2]
                    if bigram not in _STOP_WORDS:
                        tokens.append(bigram)
            i += 1
        elif ch.isalnum():
            word = ""
            while i < len(text) and text[i].isalnum():
                word += text[i]
                i += 1
            if word and word not in _STOP_WORDS:
                tokens.append(word)
        else:
            i += 1
    return tokens


def build_index(chunks: list[dict]):
    global _bm25, _corpus, _tokenized, _built
    with _lock:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25 未安装，跳过 BM25 索引")
            _built = True
            return

        _corpus = chunks
        _tokenized = [tokenize(c.get("text", "") + " " + c.get("title", "")) for c in chunks]
        _bm25 = BM25Okapi(_tokenized)
        _built = True
        logger.info("BM25 索引构建完成: %d 个文档", len(chunks))


def bm25_search(query: str, top_n: int = 15) -> list[dict]:
    if not _built or _bm25 is None:
        return []

    tokens = tokenize(query)
    if not tokens:
        return []

    scores = _bm25.get_scores(tokens)
    top_k = min(top_n, len(scores))
    top_indices = np.argpartition(scores, -top_k)[-top_k:]
    top_indices = top_indices[np.argsort(-scores[top_indices])]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            continue
        chunk = _corpus[idx]
        results.append({
            "chunk_id": chunk["chunk_id"],
            "title": chunk.get("title", ""),
            "score": score,
            "text": chunk.get("text", ""),
            "source_path": chunk.get("source_path", ""),
            "source_type": chunk.get("source_type", ""),
            "category": chunk.get("category", ""),
            "tags": chunk.get("tags", []),
            "priority": chunk.get("priority", 3),
        })

    return results


def clear():
    global _bm25, _corpus, _tokenized, _built
    _bm25 = None
    _corpus = []
    _tokenized = []
    _built = False

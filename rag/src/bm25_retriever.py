"""
bm25_retriever.py — BM25 稀疏检索器

使用 rank_bm25 库实现 Okapi BM25 算法，作为 FTS5 的替代/补充。
对中文文本做智能分词后索引。
"""

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
        elif ch.isascii() and ch.isalnum():
            # 注意：不能只用 isalnum() —— 中文的 isalnum() 也是 True，
            # 那样 "ai写作需要去ai味" 整串会被当成一个 ASCII 词吞掉。
            word = ""
            while i < len(text) and text[i].isascii() and text[i].isalnum():
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


def ensure_index() -> bool:
    """确保 BM25 索引可用（查询进程首次检索时从 SQLite 懒构建）。

    BM25 索引只存在于进程内存、不落盘；而 build_index() 此前只在
    indexer.build_full_index() 里被调用过。于是查询端（HTTP / MCP 服务）
    进程内根本没有索引，bm25_search() 恒返回空 —— 这整条稀疏召回通道
    会静默失效（retriever 里 _BM25_WEIGHT 权重照算不误，只是永远拿不到分）。

    代价落在首次检索上；服务启动的 warmup 本来就会跑一次检索，
    因此实际相当于把重建放在启动阶段完成。

    返回 True 表示索引可用。
    """
    if _built and _bm25 is not None:
        return True
    # rank_bm25 缺失时 build_index 会把 _built 置 True 但 _bm25 仍为 None，
    # 这种情况下不再反复尝试。
    if _built:
        return False

    try:
        from .storage import sqlite_store  # 延迟导入，避免 storage 与本模块循环依赖
        chunks = sqlite_store.get_all_chunks()
    except Exception as exc:  # noqa: BLE001
        logger.warning("BM25 懒加载失败: %s", exc)
        return False

    if chunks:
        logger.info("BM25 索引未构建，从 SQLite 懒加载 %d 个 chunk", len(chunks))
        build_index(chunks)

    return _built and _bm25 is not None


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

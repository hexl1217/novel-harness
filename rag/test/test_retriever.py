"""
test_retriever.py — 混合检索器测试
"""

import json
import numpy as np
import pytest

from rag.src import bm25_retriever
from rag.src.retriever import hybrid_retrieve
from rag.src.storage import sqlite_store, vector_store


VECTOR_DIM = vector_store.VECTOR_DIM


def _make_random_vector(seed=0):
    rng = np.random.RandomState(seed)
    v = rng.randn(VECTOR_DIM).astype(np.float32)
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return v.tolist()


@pytest.fixture(autouse=True)
def seed_data():
    sqlite_store.clear_all()
    sqlite_store.initialize()
    vector_store.clear()
    bm25_retriever.clear()

    chunks = [
        {
            "chunk_id": "test.doc.sec1",
            "doc_id": "test.doc",
            "title": "去AI味最小修改指南",
            "chunk_type": "rule",
            "text": "减少解释腔、自问自答、过度因果和段尾总结。用短句替代长句。",
            "category": "humanization",
            "stage": [],
            "scope": "common",
            "tags": ["去AI味", "润色"],
            "priority": 1,
            "source_type": "rule",
            "source_path": ".harness/skills/human-linguistics/rules/去AI味最小修改指南.md",
            "heading_level": 2,
        },
        {
            "chunk_id": "test.doc.sec2",
            "doc_id": "test.doc",
            "title": "Outline quality checklist",
            "chunk_type": "checklist",
            "text": "Check if the outline has a clear three-act structure. Check for sufficient conflicts and reversals.",
            "category": "outline",
            "stage": [],
            "scope": "common",
            "tags": ["outline", "review"],
            "priority": 2,
            "source_type": "rule",
            "source_path": ".harness/skills/plot-review/rules/大纲质量评估清单.md",
            "heading_level": 2,
        },
    ]
    sqlite_store.insert_chunks(chunks)
    bm25_retriever.build_index(chunks)

    vector_items = [
        {"chunk_id": "test.doc.sec1", "vector": _make_random_vector(1), "text": "减少解释腔、自问自答、过度因果和段尾总结。用短句替代长句。"},
        {"chunk_id": "test.doc.sec2", "vector": _make_random_vector(2), "text": "检查大纲是否有明确的三幕结构。检查是否有足够的冲突和反转。"},
    ]
    vector_store.insert_vectors(vector_items)

    yield


class TestHybridRetriever:
    def test_retrieve_with_task_type(self):
        result = hybrid_retrieve(query="这段太像 AI 写的", task_type="humanization", top_k=3)
        assert len(result["results"]) > 0
        assert result["meta"]["task_type"] == "humanization"

    def test_retrieve_returns_valid_structure(self):
        result = hybrid_retrieve(query="大纲检查", task_type="outline_review", top_k=3)
        for r in result["results"]:
            assert all(k in r for k in ("chunk_id", "title", "score", "reason", "snippet"))

    def test_retrieve_without_task_type(self):
        result = hybrid_retrieve(query="这段太像 AI 写的")
        assert len(result["results"]) > 0

    def test_retrieve_respects_top_k(self):
        result = hybrid_retrieve(query="test", top_k=2)
        assert len(result["results"]) <= 2

    def test_retrieve_meta(self):
        result = hybrid_retrieve(query="大纲", top_k=3)
        meta = result["meta"]
        assert "total_candidates" in meta
        assert "elapsed_ms" in meta
        assert "fts_count" in meta
        assert "vector_count" in meta

    def test_retrieve_disallow_rerank(self):
        result = hybrid_retrieve(query="大纲", top_k=3, use_rerank=False)
        assert len(result["results"]) > 0

"""
test_vector_store.py — FAISS 向量存储层测试
"""

import numpy as np
import pytest

from rag.src.storage import vector_store

VECTOR_DIM = vector_store.VECTOR_DIM


def _make_vector(seed=0):
    rng = np.random.RandomState(seed)
    v = rng.randn(VECTOR_DIM).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-10
    return v.tolist()


class TestVectorStore:
    def test_empty_store(self):
        assert vector_store.get_vector_count() == 0
        assert vector_store.vector_search(_make_vector(0)) == []

    def test_insert_and_count(self):
        items = [
            {"chunk_id": "a", "vector": _make_vector(1), "text": "text a"},
            {"chunk_id": "b", "vector": _make_vector(2), "text": "text b"},
            {"chunk_id": "c", "vector": _make_vector(3), "text": "text c"},
        ]
        vector_store.insert_vectors(items)
        assert vector_store.get_vector_count() == 3

    def test_search_returns_correct_top_n(self):
        items = [
            {"chunk_id": f"chunk_{i}", "vector": _make_vector(i), "text": f"text {i}"}
            for i in range(20)
        ]
        vector_store.insert_vectors(items)
        results = vector_store.vector_search(_make_vector(0), top_n=5)
        assert len(results) == 5
        assert all("chunk_id" in r and "score" in r for r in results)

    def test_search_semantic_closest(self):
        query_vec = _make_vector(42)
        items = [
            {"chunk_id": "close", "vector": _make_vector(42), "text": "close text"},
            {"chunk_id": "far", "vector": _make_vector(999), "text": "far text"},
        ]
        vector_store.insert_vectors(items)
        results = vector_store.vector_search(query_vec, top_n=2)
        assert results[0]["chunk_id"] == "close"
        assert results[0]["score"] >= results[1]["score"]

    def test_clear(self):
        items = [
            {"chunk_id": "a", "vector": _make_vector(1), "text": "a"},
        ]
        vector_store.insert_vectors(items)
        assert vector_store.get_vector_count() == 1
        vector_store.clear()
        assert vector_store.get_vector_count() == 0

    def test_get_all_vectors(self):
        items = [
            {"chunk_id": "a", "vector": _make_vector(1), "text": "hello"},
            {"chunk_id": "b", "vector": _make_vector(2), "text": "world"},
        ]
        vector_store.insert_vectors(items)
        all_vecs = vector_store.get_all_vectors()
        assert len(all_vecs) == 2
        ids = {v["chunk_id"] for v in all_vecs}
        assert ids == {"a", "b"}

    def test_cosine_similarity_same(self):
        v = _make_vector(0)
        assert abs(vector_store.cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        a = [1.0] + [0.0] * (VECTOR_DIM - 1)
        b = [0.0] * VECTOR_DIM
        b[1] = 1.0
        assert abs(vector_store.cosine_similarity(a, b)) < 1e-6

    def test_cosine_similarity_zero(self):
        assert vector_store.cosine_similarity([0.0] * VECTOR_DIM, [1.0] * VECTOR_DIM) == 0.0

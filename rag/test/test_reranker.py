"""
test_reranker.py — CrossEncoder 重排序器测试
"""

import pytest

from rag.src import reranker


class TestReranker:
    def test_empty_candidates(self):
        assert reranker.rerank("test query", []) == []

    def test_single_candidate(self):
        candidates = [{"chunk_id": "a", "text": "some text", "score": 0.5}]
        result = reranker.rerank("test", candidates)
        assert len(result) == 1
        assert result[0]["chunk_id"] == "a"
        assert "ce_score" in result[0]

    def test_score_based_fallback(self, monkeypatch):
        monkeypatch.setattr(reranker, "_cross_encoder", None)
        monkeypatch.setattr(reranker, "_model_attempted", True)

        candidates = [
            {"chunk_id": "a", "text": "AI 写作技巧", "score": 0.8},
            {"chunk_id": "b", "text": "关于大纲的说明", "score": 0.3},
        ]
        result = reranker.rerank("AI 写作", candidates)
        assert len(result) == 2
        # a has higher score + term overlap
        assert result[0]["chunk_id"] == "a"

    def test_rerank_respects_top_n(self):
        candidates = [
            {"chunk_id": f"c{i}", "text": f"text {i}", "score": 1.0 - i * 0.1}
            for i in range(10)
        ]
        result = reranker.rerank("text", candidates, top_n=3)
        assert len(result) == 3

    def test_rerank_stable_order(self):
        candidates = [
            {"chunk_id": "a", "text": "AAA", "score": 0.9},
            {"chunk_id": "b", "text": "BBB", "score": 0.1},
            {"chunk_id": "c", "text": "CCC", "score": 0.5},
        ]
        r1 = reranker.rerank("test", candidates)
        r2 = reranker.rerank("test", candidates)
        ids1 = [c["chunk_id"] for c in r1]
        ids2 = [c["chunk_id"] for c in r2]
        assert ids1 == ids2

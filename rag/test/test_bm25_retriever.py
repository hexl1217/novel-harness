"""
test_bm25_retriever.py — BM25 稀疏检索器测试
"""

import pytest

from rag.src import bm25_retriever


@pytest.fixture(autouse=True)
def setup_bm25():
    bm25_retriever.clear()


class TestBM25Retriever:
    def test_empty_after_clear(self):
        assert bm25_retriever.bm25_search("test") == []

    def test_build_and_search(self, sample_chunks):
        bm25_retriever.build_index(sample_chunks)
        results = bm25_retriever.bm25_search("AI 味", top_n=5)
        assert len(results) > 0
        assert all(r["score"] > 0 for r in results)

    def test_search_relevance(self, sample_chunks):
        bm25_retriever.build_index(sample_chunks)
        results = bm25_retriever.bm25_search("AI 味 修改", top_n=5)
        assert len(results) > 0
        # 第一条应该与"去AI味"相关
        assert "AI" in results[0].get("text", "") or "AI" in results[0].get("title", "")

    def test_search_no_match(self, sample_chunks):
        bm25_retriever.build_index(sample_chunks)
        results = bm25_retriever.bm25_search("完全不存在的关键词xxxxx", top_n=5)
        assert len(results) == 0

    def test_tokenize(self):
        tokens = bm25_retriever.tokenize("AI写作需要去AI味")
        assert len(tokens) > 0
        assert "ai" in tokens or "写作" in tokens

    def test_clear(self, sample_chunks):
        bm25_retriever.build_index(sample_chunks)
        assert len(bm25_retriever.bm25_search("test")) > 0
        bm25_retriever.clear()
        assert bm25_retriever.bm25_search("test") == []

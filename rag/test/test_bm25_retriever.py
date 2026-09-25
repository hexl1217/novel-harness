"""
test_bm25_retriever.py — BM25 稀疏检索器测试
"""

import pytest

from rag.src import bm25_retriever


def _chunk(chunk_id, title, text, category="writing"):
    return {
        "chunk_id": chunk_id,
        "doc_id": "test.doc",
        "title": title,
        "chunk_type": "rule",
        "text": text,
        "category": category,
        "stage": [],
        "scope": "common",
        "tags": [],
        "priority": 1,
        "source_type": "rule",
        "source_path": f"test/{chunk_id}.md",
        "heading_level": 2,
    }


@pytest.fixture
def bm25_corpus():
    """BM25 专用语料。

    语料规模必须足够大：BM25 的 IDF = log((N - n + 0.5) / (n + 0.5))，
    当 N=2、n=1 时 IDF 恰好为 0，所有文档得分都是 0，检索结果恒为空 ——
    此时断言 "检索到结果" 在数学上不可能成立。真实知识库有数百个 chunk，
    这里同样给到 6 篇以上，其中一篇含英文 token 供 test_clear 探测使用。

    注意：语料中不得出现 test_search_no_match 那条查询里的词
    （完全 / 存在 / 关键词 / 键 ……），否则该用例会失去意义。
    """
    return [
        _chunk("t.1", "去AI味最小修改指南", "减少解释腔、自问自答、过度因果和段尾总结。用短句替代长句。", "humanization"),
        _chunk("t.2", "大纲质量评估清单", "检查大纲是否有明确的三幕结构。检查是否有足够的冲突和反转。", "outline"),
        _chunk("t.3", "人物动机设计", "人物的每一次选择都要有动机支撑，避免工具人化。", "character"),
        _chunk("t.4", "对话写作要点", "对话要推动情节，避免信息倾倒和书面语腔调。", "dialogue"),
        _chunk("t.5", "场景描写技法", "场景描写要贴合人物情绪，不要堆砌比喻与铺陈。", "scene"),
        _chunk("t.6", "节奏控制方法", "长短句交替使用，情节高潮放慢，过渡段落加快。", "pacing"),
        _chunk("t.7", "Test Section", "This is a test section used to verify retrieval works.", "writing"),
    ]


class TestBM25Retriever:
    def test_empty_after_clear(self):
        assert bm25_retriever.bm25_search("test") == []

    def test_build_and_search(self, bm25_corpus):
        bm25_retriever.build_index(bm25_corpus)
        results = bm25_retriever.bm25_search("AI 味", top_n=5)
        assert len(results) > 0
        assert all(r["score"] > 0 for r in results)

    def test_search_relevance(self, bm25_corpus):
        bm25_retriever.build_index(bm25_corpus)
        results = bm25_retriever.bm25_search("AI 味 修改", top_n=5)
        assert len(results) > 0
        # 第一条应该与"去AI味"相关
        assert "AI" in results[0].get("text", "") or "AI" in results[0].get("title", "")

    def test_search_no_match(self, bm25_corpus):
        bm25_retriever.build_index(bm25_corpus)
        results = bm25_retriever.bm25_search("完全不存在的关键词xxxxx", top_n=5)
        assert len(results) == 0

    def test_tokenize(self):
        tokens = bm25_retriever.tokenize("AI写作需要去AI味")
        assert len(tokens) > 0
        assert "ai" in tokens or "写作" in tokens

    def test_clear(self, bm25_corpus):
        bm25_retriever.build_index(bm25_corpus)
        assert len(bm25_retriever.bm25_search("test")) > 0
        bm25_retriever.clear()
        assert bm25_retriever.bm25_search("test") == []

"""
test_retriever.py — 混合检索器测试
"""

import json
import numpy as np
import pytest

from rag.src import bm25_retriever
from rag.src.retriever import _retrieve_fts, _screen_by_query_overlap, hybrid_retrieve
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

    def test_bm25_channel_is_always_on(self, monkeypatch):
        """回归：BM25 召回不得挂在任何开关下面。

        历史 bug：``bm25_retriever.ensure_index()`` + ``bm25_search`` 曾写在
        ``if use_rerank:`` 里。于是当时那条 ``use_rerank=False`` 的用例
        （名为「不许重排」）实际测的是「关掉整条 BM25 召回」—— 名字与行为
        完全相反。CrossEncoder 那条路径已于 2026-09-26 移除（实测有害）。

        这里直接打桩断言「通道确实被调用」，**不**依赖语料能否召回：
        ``rank_bm25`` 的 idf 是 ``log(N-freq+0.5) - log(freq+0.5)``，
        本 fixture 只有 2 个文档，freq=1 时该式恰好为 0，所有分数被
        ``bm25_search`` 里的 ``score <= 0`` 过滤掉。那是语料规模问题，
        与通道是否接通无关（真实索引 8750 段，freq=1 时 idf ≈ 8.7）。
        """
        calls = []
        real_search = bm25_retriever.bm25_search

        def spy(query, top_n=15):
            calls.append(query)
            return real_search(query, top_n)

        monkeypatch.setattr(bm25_retriever, "bm25_search", spy)
        hybrid_retrieve(query="大纲", top_k=3)
        assert calls, (
            "hybrid_retrieve 没有调用 BM25 通道 —— 它可能又被挂到某个开关下面了"
        )

    def test_no_cross_encoder_leftovers(self):
        """回归：检索主路径不得再出现 CrossEncoder 痕迹。

        该模型被移除，是因为它把候选截断到 2*top_k 且模型给出的顺序被丢弃，
        实测使 Recall@5 从 1.000 掉到 0.700。若将来有人重新接上，这里会先报警。
        （注意：词重叠初筛是**保留**的，见 TestQueryOverlapScreen。）
        """
        result = hybrid_retrieve(query="大纲", top_k=3)
        assert "rerank_used" not in result["meta"]
        for r in result["results"]:
            assert "ce_score" not in r
            assert "overlap_score" not in r


class TestFtsChannelIsQueryDriven:
    """回归：_retrieve_fts 必须真正做全文检索。

    历史 bug：只要任务路由配了 categories，它就调用 ``filter_chunks``
    （``ORDER BY priority``）**替代** ``fts_search``，返回与查询无关的固定候选
    序列，并把所有候选统一赋 -0.1 兜底分。函数名叫 fts，实际没做检索。
    """

    ROUTE = {"categories": ["humanization", "outline"], "stages": []}

    def test_ranking_is_not_priority_ordering(self):
        """全文检索的结果不应恰好等于「按 priority 列举的全量候选」。"""
        fts_ids = [r["chunk_id"] for r in _retrieve_fts("去AI味", self.ROUTE, 10)]
        priority_ids = [
            r["chunk_id"]
            for r in sqlite_store.filter_chunks(categories=self.ROUTE["categories"], top_n=10)
        ]
        assert fts_ids, "全文检索应召回候选"
        assert fts_ids != priority_ids, (
            "_retrieve_fts 返回了按 priority 排列的固定序列 —— 说明它又退回用"
            " filter_chunks 替代全文检索了"
        )

    def test_channel_equals_fts_search_when_hits_exist(self):
        """有全文命中时，FTS 路应当就是 fts_search 的结果。

        不依赖分数绝对量级（FTS5 的 bm25() 在小语料下会退化成 0 附近），
        只验证「走的确实是全文检索这条路径」。
        """
        direct = sqlite_store.fts_search("去AI味", 10)
        assert direct, "前置条件：fts_search 对中文查询应有命中"
        via_channel = _retrieve_fts("去AI味", self.ROUTE, 10)
        assert [r["chunk_id"] for r in via_channel] == [r["chunk_id"] for r in direct]

    def test_ranking_varies_with_query(self):
        """不同查询应得到不同排序（同一批类别候选下）。"""
        a = [r["chunk_id"] for r in _retrieve_fts("去AI味", self.ROUTE, 10)]
        b = [r["chunk_id"] for r in _retrieve_fts("outline", self.ROUTE, 10)]
        assert a and b
        assert a != b

    def test_falls_back_to_category_when_no_text_match(self):
        """全文检索无结果时退回类别候选，保证任务域内仍有上下文。"""
        route = {"categories": ["humanization"], "stages": []}
        rows = _retrieve_fts("zqxjv不存在的词kwmz", route, 10)
        assert rows, "无全文命中时应退回类别候选兜底"


class TestQueryOverlapScreen:
    """回归：含查询词的候选必须能被初筛保留。

    这段逻辑原先藏在 ``reranker._rerank_score_based`` 里 —— 名字是
    「CrossEncoder 不可用时的降级分支」，干的却是初筛的活。删 CrossEncoder
    时若把它一起删掉，Recall@5 会从 1.000 掉到 0.900（实见于 query
    「大纲质量评估」：正确答案落到第 6 名，与第 5 名只差 0.0036）。
    """

    def test_overlap_lifts_matching_candidate(self):
        """含查询词的候选应被提进候选短名单。"""
        candidates = [
            {"chunk_id": "a", "title": "无关高分", "text": "完全无关的内容", "score": 0.90},
            {"chunk_id": "b", "title": "无关中分", "text": "也是无关内容", "score": 0.88},
            {"chunk_id": "c", "title": "大纲质量评估清单", "text": "评估对象与五维评估", "score": 0.80},
        ]
        # 前置条件：纯按 score 取前 2 时，含查询词的 c 确实进不去 ——
        # 少了这个断言，本用例证明不了任何事。
        naive = sorted(candidates, key=lambda x: x["score"], reverse=True)[:2]
        assert "c" not in [x["chunk_id"] for x in naive]

        kept = [c["chunk_id"] for c in _screen_by_query_overlap(candidates, "大纲质量评估", top_n=2)]
        assert "c" in kept, "含查询词的候选应被初筛保留，否则会被纯 score 挤掉"

    def test_shortlist_is_bounded(self):
        """初筛结果不超过 top_n（它只是短名单，不是最终结果）。"""
        candidates = [
            {"chunk_id": f"c{i}", "title": f"标题{i}", "text": "正文", "score": 1.0 - i * 0.01}
            for i in range(50)
        ]
        assert len(_screen_by_query_overlap(candidates, "标题", top_n=10)) == 10

    def test_degenerate_inputs(self):
        assert _screen_by_query_overlap([], "q", top_n=10) == []
        one = [{"chunk_id": "a", "title": "t", "text": "x", "score": 0.5}]
        assert _screen_by_query_overlap(one, "q", top_n=10) == one

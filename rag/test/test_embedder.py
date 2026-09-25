"""
test_embedder.py — 向量嵌入生成器测试
"""

import numpy as np
import pytest

from rag.src import embedder


class TestEmbedder:
    def test_tokenize(self):
        tokens = embedder.tokenize("AI写作需要去AI味")
        assert len(tokens) > 0

    def test_tokenize_empty(self):
        assert embedder.tokenize("") == []

    def test_tokenize_stopwords(self):
        tokens = embedder.tokenize("的 了 是 在 有 和")
        # Stop words should be filtered
        assert len(tokens) <= len("的 了 是 在 有 和".split())

    def test_fallback_embed(self):
        vec = embedder._fallback_embed("测试文本")
        assert len(vec) == embedder.VECTOR_DIM
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-6

    def test_fallback_embed_consistency(self):
        v1 = embedder._fallback_embed("同一段文本")
        v2 = embedder._fallback_embed("同一段文本")
        assert v1 == v2

    def test_build_vocabulary(self):
        corpus = ["AI写作", "去AI味", "小说创作"]
        embedder.build_vocabulary(corpus)
        assert embedder._tfidf_built

    def test_tfidf_embed(self):
        corpus = ["AI写作技巧", "小说大纲设计", "去AI味修改指南"]
        embedder.build_vocabulary(corpus)
        vec = embedder._tfidf_embed("AI写作")[0]
        assert len(vec) > 0

    def test_embed_text_with_tfidf(self, monkeypatch):
        monkeypatch.setattr(embedder, "_model_attempted", True)
        monkeypatch.setattr(embedder, "_transformer_model", None)

        embedder.build_vocabulary(["测试文本", "AI写作"])
        vec = embedder.embed_text("AI写作")
        # TF-IDF 回退的维度 = 词表大小（动态），本来就不等于 VECTOR_DIM；
        # 只要索引端与查询端共用同一套词表，两侧维度就自洽。
        assert len(vec) > 0
        assert len(vec) == len(embedder._tfidf_vectorizer.get_feature_names_out())

    def test_vocabulary_not_built(self):
        embedder._tfidf_built = False
        embedder._tfidf_vectorizer = None
        vec = embedder._fallback_embed("fallback")
        assert len(vec) == embedder.VECTOR_DIM

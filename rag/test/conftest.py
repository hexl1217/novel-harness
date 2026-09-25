"""
conftest.py — pytest 共享夹具
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def isolate_storage(tmp_path, monkeypatch):
    """把所有持久化路径重定向到临时目录。

    不加这一层，测试会直接操作开发者本地的真实索引：
    - ``sqlite_store.clear_all()`` 会 DROP 掉 ``rag/data/metadata.db`` 里的
      chunks / documents / chunks_fts 表；
    - ``vector_store.clear()`` 会 unlink ``faiss.index`` / ``vectors.npy`` /
      ``meta.pkl``。

    也就是「跑一次测试 = 本地索引报废」。重定向后测试完全自包含。

    注意：下面的 clean_* 夹具都显式依赖本夹具。不能依赖 autouse 的定义顺序 ——
    pytest 实际的装配顺序并不等同于文件中的书写顺序（实测 clean_sqlite_store
    会先于本夹具执行，导致「在真实库上建表 → 再被重定向」，测试随即报
    ``no such table: chunks``）。
    """
    from rag.src.storage import sqlite_store, vector_store

    # SQLite：换库文件前必须先断开缓存的线程连接，否则 _get_db() 会继续用旧连接
    sqlite_store.close()
    monkeypatch.setattr(sqlite_store, "DB_PATH", tmp_path / "metadata.db")

    # 向量存储：路径 + 内部缓存状态一起重置，让 _ensure_loaded() 按新路径重建
    vectors_dir = tmp_path / "vectors"
    monkeypatch.setattr(vector_store, "VECTORS_DIR", vectors_dir)
    monkeypatch.setattr(vector_store, "FAISS_INDEX_PATH", vectors_dir / "faiss.index")
    monkeypatch.setattr(vector_store, "META_PATH", vectors_dir / "meta.pkl")
    monkeypatch.setattr(vector_store, "_index", None)
    monkeypatch.setattr(vector_store, "_meta", {})
    monkeypatch.setattr(vector_store, "_loaded", False)

    yield

    sqlite_store.close()


@pytest.fixture(autouse=True)
def clean_vector_store(isolate_storage):
    """每个测试前清理向量存储（作用于 isolate_storage 指定的临时目录）"""
    from rag.src.storage import vector_store
    vector_store.clear()
    yield
    vector_store.clear()


@pytest.fixture(autouse=True)
def clean_sqlite_store(isolate_storage):
    """每个测试前清理 SQLite（作用于 isolate_storage 指定的临时目录）"""
    from rag.src.storage import sqlite_store
    sqlite_store.clear_all()
    sqlite_store.initialize()
    yield
    sqlite_store.clear_all()


@pytest.fixture(autouse=True)
def clean_bm25():
    """每个测试前清理 BM25"""
    from rag.src import bm25_retriever
    bm25_retriever.clear()
    yield
    bm25_retriever.clear()


@pytest.fixture(autouse=True)
def isolate_embedder(tmp_path, monkeypatch):
    """隔离嵌入器的全局状态与落盘路径。

    1. TF-IDF 词表落盘路径改到临时目录。否则测试里的小语料会被
       ``build_vocabulary()`` 写进真正的 ``rag/data/vectors/tfidf.joblib``，
       污染同进程后续的检索测试（曾被写成 8 维词表，导致 query 维度
       与 384 维索引不匹配、向量召回整条静默失效）。
    2. 禁止加载 sentence-transformers。让嵌入行为确定（走 TF-IDF / 哈希回退），
       并避免测试期间尝试联网拉模型。
    """
    from rag.src import embedder

    monkeypatch.setattr(embedder, "TFIDF_PATH", tmp_path / "tfidf.joblib")
    monkeypatch.setattr(embedder, "_transformer_model", None)
    monkeypatch.setattr(embedder, "_model_attempted", True)
    monkeypatch.setattr(embedder, "_tfidf_vectorizer", None)
    monkeypatch.setattr(embedder, "_tfidf_built", False)
    yield


@pytest.fixture
def sample_chunk():
    return {
        "chunk_id": "test.doc.sec1",
        "doc_id": "test.doc",
        "title": "Test Section",
        "chunk_type": "definition",
        "text": "这是一段测试文本，用于验证检索功能是否正常工作。",
        "category": "writing",
        "stage": [],
        "scope": "common",
        "tags": ["test"],
        "priority": 3,
        "source_type": "knowledge",
        "source_path": "test/knowledge/test.md",
        "heading_level": 1,
    }


@pytest.fixture
def sample_chunks():
    return [
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
            "title": "大纲质量评估清单",
            "chunk_type": "checklist",
            "text": "检查大纲是否有明确的三幕结构。检查是否有足够的冲突和反转。",
            "category": "outline",
            "stage": [],
            "scope": "common",
            "tags": ["大纲", "评估"],
            "priority": 2,
            "source_type": "rule",
            "source_path": ".harness/skills/plot-review/rules/大纲质量评估清单.md",
            "heading_level": 2,
        },
    ]

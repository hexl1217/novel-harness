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


@pytest.fixture(autouse=True)
def clean_vector_store():
    """每个测试前清理向量存储"""
    from rag.src.storage import vector_store
    vector_store.clear()
    yield
    vector_store.clear()


@pytest.fixture(autouse=True)
def clean_sqlite_store():
    """每个测试前清理 SQLite"""
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

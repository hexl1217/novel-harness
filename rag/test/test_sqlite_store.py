"""
test_sqlite_store.py — SQLite + FTS5 存储层测试
"""

import json
import pytest

from rag.src.storage import sqlite_store


class TestSQLiteStore:
    def test_initialize(self):
        sqlite_store.clear_all()
        sqlite_store.initialize()
        stats = sqlite_store.get_stats()
        assert stats["documents"] == 0
        assert stats["chunks"] == 0

    def test_insert_and_get_stats(self, sample_chunk):
        sqlite_store.insert_chunks([sample_chunk])
        stats = sqlite_store.get_stats()
        assert stats["chunks"] == 1

    def test_upsert_document(self):
        doc = {
            "doc_id": "test.doc",
            "title": "Test Doc",
            "source_path": "test/doc.md",
            "source_type": "knowledge",
            "category": "writing",
            "stage": [],
            "scope": "common",
            "tags": ["test"],
            "priority": 3,
            "status": "active",
        }
        sqlite_store.upsert_document(doc)
        stats = sqlite_store.get_stats()
        assert stats["documents"] == 1

    def test_fts_search(self, sample_chunks):
        sqlite_store.insert_chunks(sample_chunks)
        results = sqlite_store.fts_search("AI 味", top_n=5)
        assert len(results) > 0
        assert results[0]["chunk_id"] in (c["chunk_id"] for c in sample_chunks)

    def test_fts_search_no_match(self, sample_chunks):
        sqlite_store.insert_chunks(sample_chunks)
        results = sqlite_store.fts_search("zzzzz_notfound", top_n=5)
        assert len(results) == 0

    def test_filter_chunks_by_category(self, sample_chunks):
        sqlite_store.insert_chunks(sample_chunks)
        results = sqlite_store.filter_chunks(categories=["humanization"], top_n=5)
        assert len(results) >= 1
        assert all(r["category"] == "humanization" for r in results)

    def test_filter_chunks_no_match(self, sample_chunks):
        sqlite_store.insert_chunks(sample_chunks)
        results = sqlite_store.filter_chunks(categories=["nonexistent"], top_n=5)
        assert len(results) == 0

    def test_get_chunk_by_id(self, sample_chunks):
        sqlite_store.insert_chunks(sample_chunks)
        chunk = sqlite_store.get_chunk_by_id("test.doc.sec1")
        assert chunk is not None
        assert chunk["chunk_id"] == "test.doc.sec1"

    def test_get_chunk_by_id_not_found(self):
        assert sqlite_store.get_chunk_by_id("nonexistent") is None

    def test_clear_all(self, sample_chunks):
        sqlite_store.insert_chunks(sample_chunks)
        sqlite_store.clear_all()
        stats = sqlite_store.get_stats()
        assert stats["documents"] == 0
        assert stats["chunks"] == 0

    def test_row_to_dict_stage_tags_parsing(self):
        sqlite_store.clear_all()
        sqlite_store.initialize()

        chunk = {
            "chunk_id": "test.sec1",
            "doc_id": "test.doc",
            "title": "Test",
            "chunk_type": "definition",
            "text": "Some text",
            "category": "writing",
            "stage": ["draft", "review"],
            "scope": "common",
            "tags": ["tag1", "tag2"],
            "priority": 2,
            "source_type": "knowledge",
            "source_path": "test.md",
            "heading_level": 1,
        }
        sqlite_store.insert_chunks([chunk])
        retrieved = sqlite_store.get_chunk_by_id("test.sec1")
        assert isinstance(retrieved["stage"], list)
        assert "draft" in retrieved["stage"]
        assert isinstance(retrieved["tags"], list)
        assert "tag1" in retrieved["tags"]

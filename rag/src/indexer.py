"""
indexer.py — 索引构建器

职责：
- 编排完整索引构建流程
- scan → normalize → chunk → buildVocabulary → embed → store
"""

import time

from .logger import get_logger
from . import bm25_retriever
from . import scanner
from . import normalizer
from . import chunker
from . import embedder
from .storage import sqlite_store
from .storage import vector_store

logger = get_logger("indexer")


def build_full_index():
    """构建完整索引

    流程：
    1. 清空旧数据（SQLite + 向量 + BM25）
    2. 初始化数据库
    3. 扫描知识文件
    4. 标准化为 document
    5. 分块为 chunks，写入 SQLite
    6. 构建 TF-IDF 词表（用于回退嵌入）
    7. 为所有 chunk 生成向量，写入向量存储
    8. 构建 BM25 稀疏索引

    返回：
        包含 documents、chunks、vectors 的统计字典
    """
    start_time = time.time()
    logger.info("=" * 50)
    logger.info("  RAG 索引构建开始")
    logger.info("=" * 50)

    # 1. 清空旧数据
    logger.info("[1/7] 清空旧数据...")
    sqlite_store.clear_all()
    vector_store.clear()
    embedder.clear_vectorizer()
    logger.info("   OK 旧数据已清空")

    # 2. 初始化数据库
    logger.info("[2/7] 初始化数据库...")
    sqlite_store.initialize()
    logger.info("   OK 数据库已初始化")

    # 3. 扫描
    logger.info("[3/7] 扫描知识文件...")
    files = scanner.scan_knowledge_files()
    logger.info("   OK 扫描到 %d 个文件", len(files))

    # 4. 标准化
    logger.info("[4/7] 标准化文档...")
    documents = []
    for f in files:
        doc = normalizer.normalize_document(f["rel_path"], f["source_type"])
        if doc:
            documents.append(doc)
            sqlite_store.upsert_document(doc)
    logger.info("   OK %d 篇文档已入库", len(documents))

    # 5. 分块
    logger.info("[5/7] 文档分块...")
    all_chunks = []
    for doc in documents:
        chunks = chunker.chunk_markdown(doc)
        all_chunks.extend(chunks)
    sqlite_store.insert_chunks(all_chunks)
    logger.info("   OK %d 个 chunks 已入库", len(all_chunks))

    # 6. 构建 TF-IDF 词表（用于回退嵌入）
    logger.info("[6/7] 构建统计嵌入词表...")
    corpus = [c["text"] for c in all_chunks]
    embedder.build_vocabulary(corpus)
    logger.info("   OK 词表构建完成")
    # 7. 生成向量
    logger.info("[7/7] 生成向量嵌入...")
    chunk_texts = [c["text"] for c in all_chunks]
    vectors = embedder.embed_batch(chunk_texts)

    vector_items = []
    for i, chunk in enumerate(all_chunks):
        vector_items.append({
            "chunk_id": chunk["chunk_id"],
            "vector": vectors[i],
            "text": chunk["text"],
        })

    vector_store.insert_vectors(vector_items)
    logger.info("   OK %d 个向量已存储", len(vector_items))

    # 8. 构建 BM25 索引
    logger.info("[8/8] 构建 BM25 稀疏索引...")
    bm25_retriever.build_index(all_chunks)
    logger.info("   OK BM25 索引构建完成")

    elapsed = time.time() - start_time
    logger.info("")
    logger.info("=" * 50)
    logger.info("  索引构建完成! (%.2fs)", elapsed)
    logger.info("  文档: %d", len(documents))
    logger.info("  Chunks: %d", len(all_chunks))
    logger.info("  向量: %d", len(vector_items))
    logger.info("  BM25: %d", len(all_chunks))
    logger.info("=" * 50)

    return {
        "documents": len(documents),
        "chunks": len(all_chunks),
        "vectors": len(vector_items),
        "bm25": len(all_chunks),
    }

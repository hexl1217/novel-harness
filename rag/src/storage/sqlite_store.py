"""
sqlite_store.py - SQLite + FTS5 存储层。
"""

import json
import sqlite3
import threading
from pathlib import Path

from ..bm25_retriever import tokenize
from ..logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

logger = get_logger("sqlite_store")
DB_PATH = PROJECT_ROOT / "rag" / "data" / "metadata.db"

_FTS_INSERT_SQL = "INSERT INTO chunks_fts (chunk_id, title, text, tags) VALUES (?, ?, ?, ?)"

_thread_local = threading.local()


def _fts_tokens(text):
    """把任意文本转成 FTS5 可检索的词序列（空格连接）。

    与 bm25_retriever 共用同一套分词（单字 + 相邻双字），
    保证 FTS 与 BM25 两条召回路径的中文粒度一致。
    """
    return " ".join(tokenize(str(text or "")))


def _get_db():
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        return conn

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    _thread_local.connection = conn
    return conn


def _fts_schema_drifted(db):
    """判断已存在的 chunks_fts 是否仍是旧版 external-content 结构。

    旧结构（content='chunks'）无法写入预分词内容，必须重建。
    """
    try:
        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'chunks_fts'"
        ).fetchone()
    except sqlite3.OperationalError:
        return False

    return bool(row and "content=" in (row["sql"] or ""))


def rebuild_fts():
    """从 chunks 表重建 FTS 检索内容。

    返回重建的 chunk 数；chunks 为空时返回 0（不报错）。
    """
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT chunk_id, title, text, tags FROM chunks"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0

    if not rows:
        return 0

    db.execute("DELETE FROM chunks_fts")
    for row in rows:
        db.execute(
            _FTS_INSERT_SQL,
            (
                row["chunk_id"],
                _fts_tokens(row["title"]),
                _fts_tokens(row["text"]),
                _fts_tokens(row["tags"]),
            ),
        )
    db.commit()
    logger.info("FTS 索引已重建: %d 个 chunk", len(rows))
    return len(rows)


def initialize():
    db = _get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK(source_type IN ('knowledge', 'rule', 'reference', 'project')),
            category TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT '[]',
            scope TEXT NOT NULL DEFAULT 'common',
            tags TEXT NOT NULL DEFAULT '[]',
            priority INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            title TEXT NOT NULL,
            chunk_type TEXT NOT NULL DEFAULT 'definition',
            text TEXT NOT NULL,
            category TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT '[]',
            scope TEXT NOT NULL DEFAULT 'common',
            tags TEXT NOT NULL DEFAULT '[]',
            priority INTEGER NOT NULL DEFAULT 3,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            heading_level INTEGER NOT NULL DEFAULT 1
        );
    """)

    # FTS5 索引表。
    #
    # 不用 FTS5 自带分词器：默认的 unicode61 把连续 CJK 字符视为同一个 token，
    # 于是 "减少解释腔" 会成为单个词，"解释腔" 这类子串永远匹配不到（中文检索全废）。
    # 改为「写入前预分词」：内容用 bm25_retriever.tokenize 分词后以空格连接存入，
    # 查询侧走同一套分词。因此表不能再是 external-content 表（那样无法注入派生内容），
    # 改为普通 FTS5 表，由 insert_chunks / rebuild_fts 填充。
    try:
        if _fts_schema_drifted(db):
            logger.info("检测到旧版 external-content 结构的 chunks_fts，重建为预分词索引")
            db.executescript("DROP TABLE IF EXISTS chunks_fts;")

        db.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                title,
                text,
                tags
            );
        """)

        rebuild_fts()
    except sqlite3.OperationalError as exc:
        logger.warning("FTS5 初始化警告: %s", exc)

    try:
        db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_chunks_category ON chunks(category);
            CREATE INDEX IF NOT EXISTS idx_chunks_priority ON chunks(priority);
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
        """)
    except sqlite3.OperationalError:
        pass

    logger.info("数据库初始化完成")


def upsert_document(doc):
    db = _get_db()
    db.execute(
        """INSERT OR REPLACE INTO documents
           (doc_id, title, source_path, source_type, category, stage, scope, tags, priority, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            doc["doc_id"],
            doc["title"],
            doc["source_path"],
            doc["source_type"],
            doc["category"],
            json.dumps(doc.get("stage", []), ensure_ascii=False),
            doc.get("scope", "common"),
            json.dumps(doc.get("tags", []), ensure_ascii=False),
            doc.get("priority", 3),
            doc.get("status", "active"),
        ),
    )
    db.commit()


def insert_chunks(chunks):
    db = _get_db()

    insert_chunk_sql = """INSERT OR REPLACE INTO chunks
        (chunk_id, doc_id, title, chunk_type, text, category, stage, scope,
         tags, priority, source_type, source_path, heading_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    insert_fts_sql = """INSERT INTO chunks_fts (chunk_id, title, text, tags)
        VALUES (?, ?, ?, ?)"""

    for chunk in chunks:
        db.execute(
            insert_chunk_sql,
            (
                chunk["chunk_id"],
                chunk["doc_id"],
                chunk["title"],
                chunk.get("chunk_type", "definition"),
                chunk["text"],
                chunk["category"],
                json.dumps(chunk.get("stage", []), ensure_ascii=False),
                chunk.get("scope", "common"),
                json.dumps(chunk.get("tags", []), ensure_ascii=False),
                chunk.get("priority", 3),
                chunk["source_type"],
                chunk["source_path"],
                chunk.get("heading_level", 1),
            ),
        )
        # FTS 存预分词结果（不是原文），否则 CJK 子串检索无效，见 initialize() 注释。
        db.execute(
            insert_fts_sql,
            (
                chunk["chunk_id"],
                _fts_tokens(chunk.get("title", "")),
                _fts_tokens(chunk["text"]),
                _fts_tokens(" ".join(chunk.get("tags", []))),
            ),
        )

    db.commit()


def _row_to_dict(row):
    if row is None:
        return None

    result = dict(row)
    for field in ("stage", "tags"):
        if field in result and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


def fts_search(query, top_n=15):
    db = _get_db()

    # 与写入侧 _fts_tokens 共用同一套分词，否则查询词与索引词不同粒度 → 永远匹配不到。
    # FTS 语法字符（: * ^ - " 等）统一用双引号包成短语规避；
    # tokenize 只产出汉字/字母数字，不会自带引号。
    terms = tokenize(str(query or ""))
    if not terms:
        return []

    # 限制词数而不是截断字符串 —— 截断会破坏引号配对，反而制造 FTS 语法错误。
    final_query = " OR ".join('"%s"' % term for term in terms[:40])

    try:
        rows = db.execute(
            """SELECT c.*, rank as fts_score
               FROM chunks_fts f
               JOIN chunks c ON c.chunk_id = f.chunk_id
               WHERE chunks_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (final_query, top_n),
        ).fetchall()

        results = []
        for row in rows:
            item = _row_to_dict(row)
            item["fts_score"] = row["fts_score"]
            results.append(item)
        return results
    except sqlite3.OperationalError as exc:
        logger.error("FTS 搜索失败: %s", exc)
        return []


def filter_chunks(categories=None, stages=None, top_n=20):
    db = _get_db()
    conditions = []
    params = []

    if categories:
        placeholders = ",".join("?" for _ in categories)
        conditions.append(f"c.category IN ({placeholders})")
        params.extend(categories)

    if stages:
        stage_conditions = []
        for stage in stages:
            stage_conditions.append("c.stage LIKE ?")
            params.append(f'%"{stage}"%')
        conditions.append(f"({' OR '.join(stage_conditions)})")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    try:
        rows = db.execute(
            f"""SELECT c.*
                FROM chunks c
                {where}
                ORDER BY c.priority ASC
                LIMIT ?""",
            (*params, top_n),
        ).fetchall()

        return [_row_to_dict(row) for row in rows]
    except sqlite3.OperationalError as exc:
        logger.error("过滤查询失败: %s", exc)
        return []


def get_chunk_by_id(chunk_id):
    db = _get_db()
    try:
        row = db.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return _row_to_dict(row) if row else None
    except sqlite3.OperationalError:
        return None


def clear_all():
    db = _get_db()
    try:
        db.executescript("""
            DROP TABLE IF EXISTS chunks_fts;
            DROP TABLE IF EXISTS chunks;
            DROP TABLE IF EXISTS documents;
        """)
        db.commit()
    except sqlite3.OperationalError:
        pass


def get_all_chunks():
    """取出全部 chunk（供 BM25 等「只在进程内存在」的索引懒构建使用）。"""
    db = _get_db()
    try:
        rows = db.execute(
            """SELECT chunk_id, doc_id, title, chunk_type, text, category, stage,
                      scope, tags, priority, source_type, source_path, heading_level
               FROM chunks"""
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    except sqlite3.OperationalError as exc:
        logger.error("读取全部 chunk 失败: %s", exc)
        return []


def get_stats():
    db = _get_db()
    try:
        doc_count = db.execute("SELECT COUNT(*) as count FROM documents").fetchone()["count"]
        chunk_count = db.execute("SELECT COUNT(*) as count FROM chunks").fetchone()["count"]
        return {"documents": doc_count, "chunks": chunk_count}
    except sqlite3.OperationalError:
        return {"documents": 0, "chunks": 0}


def close():
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.OperationalError:
            pass
        _thread_local.connection = None


def close_all():
    close()

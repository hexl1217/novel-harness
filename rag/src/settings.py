"""
settings.py — 集中配置管理

从环境变量加载配置，带默认值。所有 RAG 模块通过此模块获取配置，
而非硬编码字符串。
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# 服务
RAG_HOST: str = _env("RAG_HOST", "0.0.0.0")
RAG_PORT: int = int(_env("RAG_PORT", "3456"))
RAG_LOG_LEVEL: str = _env("RAG_LOG_LEVEL", "INFO")

# 远程知识包
REMOTE_MANIFEST: str = _env(
    "NOVEL_HARNESS_REMOTE_MANIFEST",
    "http://47.103.57.247:9000/manifest",
)

# 嵌入模型
EMBEDDING_MODEL: str = _env(
    "EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

# 重排序模型
RERANKER_MODEL: str = _env(
    "RERANKER_MODEL",
    "cross-encoder/stsb-distilroberta-base",
)

# 检索参数
RETRIEVE_TOP_K: int = int(_env("RETRIEVE_TOP_K", "5"))
RETRIEVE_FTS_N: int = int(_env("RETRIEVE_FTS_N", "30"))
RETRIEVE_VEC_N: int = int(_env("RETRIEVE_VEC_N", "30"))
RETRIEVE_BM25_N: int = int(_env("RETRIEVE_BM25_N", "30"))

# 路径
VECTORS_DIR: Path = PROJECT_ROOT / "rag" / "data" / "vectors"
DB_PATH: Path = PROJECT_ROOT / "rag" / "data" / "metadata.db"
PROJECTS_DIR: Path = PROJECT_ROOT / ".harness" / "projects"

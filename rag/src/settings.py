"""
settings.py — 集中配置管理

从项目根目录的 .env 与环境变量加载配置。所有 RAG 模块通过此模块获取配置，
而非硬编码字符串。部署相关或敏感的值（如远程知识包市场地址）不提供内置默认值，
未配置时在使用处给出明确提示，避免把内网地址写进公开仓库。
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """极简 .env 读取，避免引入第三方依赖。

    只填充尚未设置的环境变量：已存在的环境变量优先级更高，
    因此命令行与容器注入的值不会被 .env 覆盖。
    """
    env_file = path or (PROJECT_ROOT / ".env")
    if not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = value.strip().strip('"').strip("'")


load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# 服务
RAG_HOST: str = _env("RAG_HOST", "0.0.0.0")
RAG_PORT: int = int(_env("RAG_PORT", "3456"))
RAG_LOG_LEVEL: str = _env("RAG_LOG_LEVEL", "INFO")

# 远程知识包市场：无内置默认值，需通过 .env 或环境变量配置，
# 未配置时仅能使用内置知识包
REMOTE_MANIFEST: str = _env("NOVEL_HARNESS_REMOTE_MANIFEST")

# 嵌入模型
EMBEDDING_MODEL: str = _env(
    "EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
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

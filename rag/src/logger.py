"""
logger.py — RAG 统一日志器

所有 RAG 模块通过此 logger 输出日志，
不再使用 print()。
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"novel-harness.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            fmt="[%(name)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

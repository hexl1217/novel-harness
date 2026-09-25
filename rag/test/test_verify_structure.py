"""
test_verify_structure.py — 从 verify.py 抽出的「不依赖索引」验收检查。

verify.py 是一个完整的验收脚本（50+ 项检查），但此前从未被任何流程调用：
CI 里 0 处引用，文件名也不以 test_ 开头，pytest 默认不会收集它。

这里把它当中**不依赖索引**的三组检查转成 pytest，让它们每次 CI 都跑：

  1. 架构完整性 —— 必需文件是否存在
  2. 知识源扫描 —— 是否扫到文件、是否漏扫禁入路径
  3. 任务路由 —— 7 类任务的 route_query 是否正确

依赖索引的部分（索引构建、混合检索、结果稳定性）留在 verify.py 内，
由 CI 的 verify-rag job 在构建索引后以 --no-build 执行。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.src.router import route_query
from rag.src.scanner import scan_knowledge_files


REQUIRED_FILES = [
    "rag/src/__init__.py",
    "rag/src/storage/__init__.py",
    "rag/src/scanner.py",
    "rag/src/normalizer.py",
    "rag/src/chunker.py",
    "rag/src/embedder.py",
    "rag/src/router.py",
    "rag/src/retriever.py",
    "rag/src/context_pack.py",
    "rag/src/indexer.py",
    "rag/src/server.py",
    "rag/src/storage/sqlite_store.py",
    "rag/src/storage/vector_store.py",
    "rag/scripts/build_index.py",
    "rag/scripts/query.py",
    "rag/scripts/ingest.py",
    "rag/config/sources.json",
    "rag/config/task-routes.json",
    "rag/config/categories.json",
    "rag/schemas/document.schema.json",
    "rag/schemas/chunk.schema.json",
    "rag/schemas/context-pack.schema.json",
]

FORBIDDEN_DIR_SEGMENTS = ["planning", "legacy-skills", "agents", "memory", "cases"]
FORBIDDEN_PATH_PREFIXES = [".harness/rules/"]

ROUTE_CASES = [
    ("这段太像 AI 写的", "humanization"),
    ("这个大纲后面能不能展开", "outline_review"),
    ("这一章写之前我该准备什么", "chapter_prewrite"),
    ("全民求生该先定哪条路线", "genre_routing"),
    ("这章节奏太平了，读起来很拖", "rhythm_review"),
    ("帮我看看角色状态有没有矛盾", "consistency_check"),
    ("给我一些新的灵感", "ideation"),
]


@pytest.fixture(scope="module")
def scanned_files():
    """扫描一次复用：glob 900+ 文件，逐用例重扫太浪费。"""
    return scan_knowledge_files()


class TestArchitectureIntegrity:
    @pytest.mark.parametrize("rel_path", REQUIRED_FILES)
    def test_required_file_exists(self, rel_path):
        assert (PROJECT_ROOT / rel_path).exists(), f"缺少必需文件: {rel_path}"


class TestKnowledgeScan:
    def test_scan_finds_files(self, scanned_files):
        assert len(scanned_files) > 0, "知识源扫描结果为空"

    def test_no_forbidden_dir_segments(self, scanned_files):
        for segment in FORBIDDEN_DIR_SEGMENTS:
            hits = [
                f["rel_path"] for f in scanned_files
                if segment in Path(f["rel_path"]).parts
            ]
            assert not hits, f"扫描到了禁入目录段 {segment!r}: {hits[:5]}"

    def test_no_forbidden_path_prefixes(self, scanned_files):
        for prefix in FORBIDDEN_PATH_PREFIXES:
            hits = [
                f["rel_path"] for f in scanned_files
                if f["rel_path"].startswith(prefix)
            ]
            assert not hits, f"扫描到了禁入路径 {prefix!r}: {hits[:5]}"

    def test_has_rule_and_reference_types(self, scanned_files):
        types = {f["source_type"] for f in scanned_files}
        assert "rule" in types, "扫描结果中没有 rule 类型文件"
        assert "reference" in types, "扫描结果中没有 reference 类型文件"

    def test_rel_paths_are_normalized(self, scanned_files):
        """rel_path 必须是正斜杠、且不含反斜杠——索引与检索都按此约定。"""
        bad = [f["rel_path"] for f in scanned_files if "\\" in f["rel_path"]]
        assert not bad, f"rel_path 未规范化: {bad[:5]}"


class TestTaskRouting:
    @pytest.mark.parametrize("query,expected", ROUTE_CASES)
    def test_route_query(self, query, expected):
        route = route_query(query)
        actual = route.get("task_type")
        assert actual == expected, (
            f"路由错误: {query!r} 期望 {expected}, 实际 {actual}"
            f"（置信度 {route.get('confidence', 0):.2f}）"
        )

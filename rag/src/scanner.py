"""
scanner.py - 知识源文件扫描器。

扫描本地知识包、skill 规则/参考文档和项目模板，
输出相对路径与标准化 source_type。
"""

from pathlib import Path

from .logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = get_logger("scanner")

INCLUDE_PATTERNS = [
    ".harness/knowledge/included/**/*.md",
    ".harness/knowledge/remote/**/*.md",
    ".harness/knowledge/remote/**/*.txt",
    ".harness/skills/**/references/*.md",
    ".harness/skills/**/rules/*.md",
    ".harness/project-templates/*.md",
]

# 排除规则：按「路径段精确相等」匹配。
#
# 历史实现是 ["*planning*", "*agents*", ...] 这类 glob，经 _glob_to_regex
# 把 "*" 译成 [^/]*（不跨目录），"*planning*" 实际等价于
# ^[^/]*planning[^/]*$ —— 只能匹配不含 "/" 的单层文件名，
# 对任何多级路径恒为假。原 9 条排除规则里有 6 条因此完全失效。
#
# 改为段精确匹配后：
#   * 真正的 planning/ 目录会被正确排除；
#   * 名字里含 planning 的知识包（如 webnovel-creative-planning）
#     不会被误杀——它本来就应该被索引。
#
# 注意 rag/config/sources.json 里的 include/exclude 目前**不被本模块读取**，
# 两侧内容需人工保持一致。
EXCLUDE_DIR_SEGMENTS = frozenset({
    "planning",
    "legacy-skills",
    "agents",
    "memory",
    "cases",
    "user",
    "current-project",
})

EXCLUDE_PATH_PREFIXES = (
    ".harness/rules/",
)

EXCLUDE_FILE_PREFIXES = ("README",)


def _is_excluded(rel_path: str) -> bool:
    """判断相对路径是否命中排除规则。"""
    if rel_path.startswith(EXCLUDE_PATH_PREFIXES):
        return True

    parts = Path(rel_path).parts
    if any(segment in EXCLUDE_DIR_SEGMENTS for segment in parts):
        return True

    name = parts[-1] if parts else ""
    return any(name.upper().startswith(prefix) for prefix in EXCLUDE_FILE_PREFIXES)


def _infer_source_type(pattern):
    if "/knowledge/" in pattern:
        return "knowledge"
    if "/rules/" in pattern:
        return "rule"
    if "/references/" in pattern:
        return "reference"
    if "/project-templates/" in pattern:
        return "project"
    return "reference"


def scan_knowledge_files():
    """扫描所有可索引的知识文件。"""
    results = []

    for pattern in INCLUDE_PATTERNS:
        source_type = _infer_source_type(pattern)
        matched_files = [p for p in PROJECT_ROOT.glob(pattern) if p.is_file()]

        for file_path in matched_files:
            rel_path = str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if _is_excluded(rel_path):
                continue

            results.append({
                "rel_path": rel_path,
                "source_type": source_type,
            })

    seen = set()
    unique = []
    for item in results:
        if item["rel_path"] not in seen:
            seen.add(item["rel_path"])
            unique.append(item)

    unique.sort(key=lambda x: x["rel_path"])
    logger.info("扫描到 %d 个知识文件", len(unique))
    return unique

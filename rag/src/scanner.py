"""
scanner.py - 知识源文件扫描器。

扫描本地知识包、skill 规则/参考文档和项目模板，
输出相对路径与标准化 source_type。

扫描范围由 ``rag/config/sources.json`` 驱动（include_patterns / exclude /
source_types）。该文件此前只是「文档性质」的配置——没有任何代码读它，
本模块硬编码了一份同名规则，改配置不生效、两边容易漂移。现在配置是真源。

配置缺失或损坏时回退到本模块的内置默认值，避免一个坏配置把知识库扫成空。
"""

import json
from fnmatch import fnmatch
from pathlib import Path

from .logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_CONFIG_PATH = PROJECT_ROOT / "rag" / "config" / "sources.json"

logger = get_logger("scanner")

# ---------------------------------------------------------------------------
# 内置默认值：仅当 sources.json 不可用时使用。
# 修改扫描范围请改 rag/config/sources.json，不要改这里。
# ---------------------------------------------------------------------------
_DEFAULT_INCLUDE_PATTERNS = [
    ".harness/knowledge/included/**/*.md",
    ".harness/knowledge/remote/**/*.md",
    ".harness/knowledge/remote/**/*.txt",
    ".harness/skills/**/references/*.md",
    ".harness/skills/**/rules/*.md",
    ".harness/project-templates/*.md",
]

_DEFAULT_SOURCE_TYPES = {
    "knowledge": ".harness/knowledge/**/*.md",
    "reference": ".harness/skills/**/references/*.md",
    "rule": ".harness/skills/**/rules/*.md",
    "project": ".harness/project-templates/*.md",
}

_DEFAULT_EXCLUDE = {
    "path_prefixes": [".harness/rules/"],
    # 按「路径段精确相等」匹配。
    #
    # 历史实现是 ["*planning*", "*agents*", ...] 这类 glob，经 _glob_to_regex
    # 把 "*" 译成 [^/]*（不跨目录），"*planning*" 实际等价于
    # ^[^/]*planning[^/]*$ —— 只能匹配不含 "/" 的单层文件名，
    # 对任何多级路径恒为假。原 9 条排除规则里有 6 条因此完全失效。
    #
    # 段精确匹配下，真正的 planning/ 目录会被排除，而名字里含 planning 的
    # 知识包（如 webnovel-creative-planning）不会被误杀——它本就该被索引。
    "dir_segments": [
        "planning",
        "legacy-skills",
        "agents",
        "memory",
        "cases",
        "user",
        "current-project",
        "node_modules",
    ],
    "file_prefixes": ["README"],
}


def _load_sources_config():
    """读取 sources.json。返回 dict，失败时返回空 dict 交由调用方回退。"""
    try:
        data = json.loads(SOURCES_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s 不存在，使用内置默认扫描配置", SOURCES_CONFIG_PATH.name)
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("%s 不可解析(%s)，使用内置默认扫描配置",
                       SOURCES_CONFIG_PATH.name, exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("%s 顶层不是对象，使用内置默认扫描配置", SOURCES_CONFIG_PATH.name)
        return {}
    return data


def _pick(container, key, default):
    """从配置里取一个可用的列表/映射，取不到时用默认值。"""
    value = container.get(key)
    if isinstance(value, (list, dict)) and value:
        return value
    return default


_CONFIG = _load_sources_config()

INCLUDE_PATTERNS = _pick(_CONFIG, "include_patterns", _DEFAULT_INCLUDE_PATTERNS)
SOURCE_TYPES = _pick(_CONFIG, "source_types", _DEFAULT_SOURCE_TYPES)

_exclude_cfg = _CONFIG.get("exclude")
if not isinstance(_exclude_cfg, dict):
    _exclude_cfg = {}

EXCLUDE_PATH_PREFIXES = tuple(
    _pick(_exclude_cfg, "path_prefixes", _DEFAULT_EXCLUDE["path_prefixes"])
)
EXCLUDE_DIR_SEGMENTS = frozenset(
    _pick(_exclude_cfg, "dir_segments", _DEFAULT_EXCLUDE["dir_segments"])
)
EXCLUDE_FILE_PREFIXES = tuple(
    _pick(_exclude_cfg, "file_prefixes", _DEFAULT_EXCLUDE["file_prefixes"])
)


def _is_excluded(rel_path: str) -> bool:
    """判断相对路径是否命中排除规则。"""
    if rel_path.startswith(EXCLUDE_PATH_PREFIXES):
        return True

    parts = Path(rel_path).parts
    if any(segment in EXCLUDE_DIR_SEGMENTS for segment in parts):
        return True

    name = parts[-1] if parts else ""
    return any(name.upper().startswith(prefix.upper()) for prefix in EXCLUDE_FILE_PREFIXES)


def _infer_source_type(rel_path: str) -> str:
    """判定文件的 source_type。

    优先按配置 ``source_types`` 的 glob 匹配文件路径；不命中时按路径段兜底。
    兜底是必要的：``source_types["knowledge"]`` 只声明了 ``*.md``，而 include
    范围内还有 ``.harness/knowledge/remote/**/*.txt``，那些文件同样属于知识包。
    """
    for source_type, pattern in SOURCE_TYPES.items():
        if fnmatch(rel_path, pattern):
            return source_type

    parts = rel_path.split("/")
    if "knowledge" in parts:
        return "knowledge"
    if "rules" in parts:
        return "rule"
    if "references" in parts:
        return "reference"
    if "project-templates" in parts:
        return "project"
    return "reference"


def scan_knowledge_files():
    """扫描所有可索引的知识文件。"""
    results = []

    for pattern in INCLUDE_PATTERNS:
        matched_files = [p for p in PROJECT_ROOT.glob(pattern) if p.is_file()]

        for file_path in matched_files:
            rel_path = str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if _is_excluded(rel_path):
                continue

            results.append({
                "rel_path": rel_path,
                "source_type": _infer_source_type(rel_path),
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

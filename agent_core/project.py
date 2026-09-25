"""
project.py — 小说项目管理

维护项目元数据、当前状态、角色档案、伏笔追踪等。
数据持久化到 .harness/projects/{project_name}/ 下。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 与 .harness/rules/maps/draft-output-map.md 的约定对齐：
# 创作目录在仓库根的 projects/ 下，不在 .harness/projects/ 下。
PROJECTS_DIR = PROJECT_ROOT / "projects"


@dataclass
class CharacterState:
    name: str
    role: str = "主角"
    status: str = "活跃"
    level: int = 1
    attributes: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class PlotThread:
    thread_id: str
    description: str
    status: str = "开放"  # 开放 | 发展中 | 已收束
    related_chapters: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ChapterRecord:
    chapter_num: int
    title: str
    word_count: int = 0
    status: str = "未开始"  # 未开始 | 写作中 | 审稿中 | 已完成
    file_path: str = ""
    summary: str = ""
    created_at: str = ""


@dataclass
class Project:
    name: str
    genre: str = ""
    platform: str = ""
    protagonist: str = ""
    world_setting: str = ""
    outline: str = ""
    target_word_count: int = 2000
    chapters: list[ChapterRecord] = field(default_factory=list)
    characters: list[CharacterState] = field(default_factory=list)
    plot_threads: list[PlotThread] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        chapters = [ChapterRecord(**c) for c in data.get("chapters", [])]
        characters = [CharacterState(**c) for c in data.get("characters", [])]
        plot_threads = [PlotThread(**t) for t in data.get("plot_threads", [])]
        return cls(
            name=data["name"],
            genre=data.get("genre", ""),
            platform=data.get("platform", ""),
            protagonist=data.get("protagonist", ""),
            world_setting=data.get("world_setting", ""),
            outline=data.get("outline", ""),
            target_word_count=data.get("target_word_count", 2000),
            chapters=chapters,
            characters=characters,
            plot_threads=plot_threads,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class ProjectStore:
    """项目管理器，负责项目的 CRUD 和持久化

    存储约定（与 .harness/rules/maps/draft-output-map.md 对齐）：

        {base_dir}/{项目名}/project.json    引擎自己的项目状态
        {base_dir}/{项目名}/正文/第N章.md   正文文件

    注意：project.json 只承载引擎状态，不碰 Agent 维护的「项目档案.md」，
    避免用 JSON 覆盖人工撰写的项目说明。
    """

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or PROJECTS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        return name.strip().replace(" ", "_").replace("/", "_")

    def _project_dir(self, name: str) -> Path:
        return self.base_dir / self._safe_name(name)

    def _project_path(self, name: str) -> Path:
        return self._project_dir(name) / "project.json"

    def chapter_path(self, name: str, chapter_num: int) -> Path:
        """正文文件路径：{项目目录}/正文/第N章.md"""
        return self._project_dir(name) / "正文" / f"第{chapter_num}章.md"

    def save(self, project: Project) -> None:
        path = self._project_path(project.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        project.updated_at = datetime.datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, name: str) -> Project | None:
        path = self._project_path(name)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Project.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            print(f"[ProjectStore] 加载 '{name}' 失败: {e}")
            return None

    def list_projects(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return sorted(
            d.name for d in self.base_dir.iterdir()
            if d.is_dir() and (d / "project.json").exists()
        )

    def delete(self, name: str) -> bool:
        path = self._project_path(name)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False

    def exists(self, name: str) -> bool:
        return self._project_path(name).exists()

    def set_current(self, name: str) -> None:
        """更新当前项目指针，保留文件里已有的备注。

        current-project.md 由用户和 Agent 共同维护，除项目名外通常还带
        进度说明、上一个项目等备注。这里只替换项目名行，其余原样保留，
        避免整文件覆盖丢内容。
        """
        current_path = PROJECT_ROOT / ".harness" / "current-project.md"
        current_path.parent.mkdir(parents=True, exist_ok=True)

        header = "# 当前项目"
        preserved: list[str] = []
        if current_path.exists():
            try:
                existing = current_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                existing = []
            if existing and existing[0].strip().startswith(header):
                existing = existing[1:]
            while existing and not existing[0].strip():
                existing.pop(0)
            # 丢弃旧的项目名行，但保留备注块（> 开头）和后续小节
            if existing and not existing[0].lstrip().startswith(("#", ">")):
                existing.pop(0)
            while existing and not existing[0].strip():
                existing.pop(0)
            preserved = existing

        lines = [header, "", name]
        if preserved:
            lines.append("")
            lines.extend(preserved)
        current_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def get_current(self) -> str | None:
        """读取当前项目名。

        指针行可能带括号说明（如「书名（项目目录：`projects/xxx/`）」），
        这里只取项目名部分，与 set_current 写入的值保持对称。
        """
        current_path = PROJECT_ROOT / ".harness" / "current-project.md"
        if not current_path.exists():
            return None
        try:
            for line in current_path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith(("#", ">")):
                    continue
                return text.split("（")[0].split("(")[0].strip()
        except OSError:
            pass
        return None

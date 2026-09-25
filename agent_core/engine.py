"""
engine.py — 小说创作管线引擎

通过有限状态机强制执行创作管线，确保：
- 必须先开书规划，才能写正文
- 必须先写正文，才能审稿
- 必须先审稿（或跳过），才能继续写下一章
- 任何状态转换不符合规则都会被阻止
"""

from __future__ import annotations

from enum import Enum, auto
import datetime
from pathlib import Path
from typing import Any

from .project import CharacterState, ChapterRecord, PlotThread, Project, ProjectStore
from .state_machine import StateMachine, StateTransitionError


class PipelineState(Enum):
    IDLE = auto()
    PROJECT_INIT = auto()
    PLANNING = auto()
    WRITING = auto()
    REVIEWING = auto()
    REVISING = auto()
    COMPLETED = auto()


class NovelPipelineEngine:
    """小说创作管线引擎

    用法：
        engine = NovelPipelineEngine()
        engine.initialize("书名", genre="玄幻")
        engine.start_planning(outline="...")
        engine.write_chapter("第一章内容...")
        engine.request_review()
        engine.approve_chapter()
    """

    def __init__(self, store: ProjectStore | None = None):
        self.store = store or ProjectStore()
        self.project: Project | None = None
        self._current_chapter: int = 0
        self._sm = StateMachine(initial_state=PipelineState.IDLE)
        self._setup_state_machine()
        self._error: str | None = None

    def _setup_state_machine(self) -> None:
        sm = self._sm

        # IDLE → PROJECT_INIT（用户说"帮我写小说"）
        sm.add_transition(PipelineState.IDLE, PipelineState.PROJECT_INIT)

        # PROJECT_INIT → PLANNING（项目信息确认后）
        sm.add_transition(PipelineState.PROJECT_INIT, PipelineState.PLANNING)

        # PLANNING → WRITING（大纲确认后）
        sm.add_transition(PipelineState.PLANNING, PipelineState.WRITING)

        # WRITING → REVIEWING（一章写完后）
        sm.add_transition(PipelineState.WRITING, PipelineState.REVIEWING)

        # WRITING → PLANNING（用户想改大纲）
        sm.add_transition(PipelineState.WRITING, PipelineState.PLANNING)

        # REVIEWING → REVISING（审稿发现问题）
        sm.add_transition(PipelineState.REVIEWING, PipelineState.REVISING)

        # REVIEWING → WRITING（审稿通过，继续写下一章）
        sm.add_transition(PipelineState.REVIEWING, PipelineState.WRITING)

        # REVIEWING → COMPLETED（全书完成）
        sm.add_transition(PipelineState.REVIEWING, PipelineState.COMPLETED)

        # REVISING → REVIEWING（修改完成，重新审稿）
        sm.add_transition(PipelineState.REVISING, PipelineState.REVIEWING)

        # REVISING → WRITING（直接继续）
        sm.add_transition(PipelineState.REVISING, PipelineState.WRITING)

        # 任意状态回到 PLANNING（用户主动要求改大纲）
        for state in (PipelineState.WRITING, PipelineState.REVIEWING, PipelineState.REVISING):
            sm.add_transition(state, PipelineState.PLANNING)

        # 添加守卫条件
        sm.add_guard(
            PipelineState.PROJECT_INIT,
            PipelineState.PLANNING,
            lambda: self.project is not None and bool(self.project.name),
        )
        sm.add_guard(
            PipelineState.PLANNING,
            PipelineState.WRITING,
            lambda: self.project is not None and bool(self.project.outline),
        )

    @property
    def state(self) -> PipelineState:
        return self._sm.current or PipelineState.IDLE

    @property
    def error(self) -> str | None:
        return self._error

    def reset(self) -> None:
        self._sm.reset(PipelineState.IDLE)
        self.project = None
        self._current_chapter = 0
        self._error = None

    # ======== 管线操作 ========

    def initialize(self, name: str, genre: str = "", platform: str = "",
                   protagonist: str = "", world_setting: str = "",
                   target_word_count: int = 2000) -> bool:
        try:
            self._sm.transition_to(PipelineState.PROJECT_INIT)
        except StateTransitionError as e:
            self._error = str(e)
            return False

        self.project = Project(
            name=name,
            genre=genre,
            platform=platform,
            protagonist=protagonist,
            world_setting=world_setting,
            target_word_count=target_word_count,
            created_at=datetime.datetime.now().isoformat(),
        )
        self.store.save(self.project)
        self.store.set_current(name)
        self._error = None
        return True

    def start_planning(self, outline: str) -> bool:
        if self.state not in (PipelineState.PROJECT_INIT, PipelineState.WRITING,
                              PipelineState.REVIEWING, PipelineState.REVISING):
            self._error = f"当前状态不允许规划: {self.state}"
            return False

        try:
            self._sm.transition_to(PipelineState.PLANNING)
        except StateTransitionError as e:
            self._error = str(e)
            return False

        if self.project:
            self.project.outline = outline
            self.store.save(self.project)
        self._error = None
        return True

    def write_chapter(self, title: str, content: str, word_count: int | None = None) -> bool:
        # 已在 WRITING 态时继续写下一章属于正常流程（审稿通过 → 写第 N+1 章），
        # 但状态机不定义自转换，所以只在非 WRITING 态才做转换。
        if self.state is not PipelineState.WRITING:
            try:
                self._sm.transition_to(PipelineState.WRITING)
            except StateTransitionError as e:
                self._error = str(e)
                return False

        chapter_num = self._current_chapter + 1

        # 落盘门禁：对齐 .harness/rules/maps/draft-output-map.md
        # 已存在的正文文件不覆盖，避免抹掉作者已写内容。
        file_path: Path | None = None
        if self.project:
            target = self.store.chapter_path(self.project.name, chapter_num)
            if target.exists():
                self._error = f"正文文件已存在，未覆盖：{target}"
                return False
            file_path = target

        try:
            if file_path is not None:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(
                    f"# 第{chapter_num}章 {title}\n\n{content}", encoding="utf-8"
                )
        except OSError as e:
            self._error = f"写入正文失败：{e}"
            return False

        self._current_chapter = chapter_num
        chapter = ChapterRecord(
            chapter_num=chapter_num,
            title=title,
            word_count=word_count or len(content),
            status="写作中",
            file_path=str(file_path) if file_path else "",
            created_at=datetime.datetime.now().isoformat(),
        )
        if self.project:
            self.project.chapters.append(chapter)
            self.store.save(self.project)

        self._error = None
        return True

    def request_review(self) -> bool:
        try:
            self._sm.transition_to(PipelineState.REVIEWING)
        except StateTransitionError as e:
            self._error = str(e)
            return False

        if self.project and self.project.chapters:
            self.project.chapters[-1].status = "审稿中"
            self.store.save(self.project)
        self._error = None
        return True

    def approve_chapter(self, revisions_needed: bool = False) -> bool:
        """批准当前章节

        Args:
            revisions_needed: 是否需要修改
        """
        if revisions_needed:
            try:
                self._sm.transition_to(PipelineState.REVISING)
            except StateTransitionError as e:
                self._error = str(e)
                return False
            if self.project and self.project.chapters:
                self.project.chapters[-1].status = "修改中"
        else:
            try:
                self._sm.transition_to(PipelineState.WRITING)
            except StateTransitionError as e:
                self._error = str(e)
                return False
            if self.project and self.project.chapters:
                self.project.chapters[-1].status = "已完成"

        if self.project:
            self.store.save(self.project)
        self._error = None
        return True

    def complete_revision(self) -> bool:
        """修改完成，回到审查"""
        try:
            self._sm.transition_to(PipelineState.REVIEWING)
        except StateTransitionError as e:
            self._error = str(e)
            return False
        self._error = None
        return True

    def finish_novel(self) -> bool:
        try:
            self._sm.transition_to(PipelineState.COMPLETED)
        except StateTransitionError as e:
            self._error = str(e)
            return False
        if self.project and self.project.chapters:
            self.project.chapters[-1].status = "已完成"
            self.store.save(self.project)
        self._error = None
        return True

    # ======== 辅助方法 ========

    def get_state_info(self) -> dict[str, Any]:
        allowed = [s.name for s in self._sm.get_allowed_transitions()]
        return {
            "current_state": self.state.name,
            "allowed_transitions": allowed,
            "project_name": self.project.name if self.project else None,
            "chapter_count": self._current_chapter,
            "current_chapter": self._current_chapter,
            "last_error": self._error,
        }

    def add_character(self, name: str, role: str = "主角", **kwargs: Any) -> bool:
        if not self.project:
            self._error = "没有活跃项目"
            return False
        char = CharacterState(name=name, role=role, **kwargs)
        self.project.characters.append(char)
        self.store.save(self.project)
        self._error = None
        return True

    def add_plot_thread(self, thread_id: str, description: str) -> bool:
        if not self.project:
            self._error = "没有活跃项目"
            return False
        thread = PlotThread(thread_id=thread_id, description=description)
        self.project.plot_threads.append(thread)
        self.store.save(self.project)
        self._error = None
        return True

    def load_project(self, name: str) -> bool:
        project = self.store.load(name)
        if project is None:
            self._error = f"项目 '{name}' 不存在"
            return False
        self.project = project
        self._current_chapter = len(project.chapters)
        self._sm.reset(PipelineState.WRITING)
        self.store.set_current(name)
        self._error = None
        return True

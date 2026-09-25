"""
test_engine.py — 小说创作管线引擎测试
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.engine import NovelPipelineEngine, PipelineState, StateTransitionError
from agent_core.project import Project, ProjectStore


@pytest.fixture
def engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ProjectStore(base_dir=Path(tmpdir))
        eng = NovelPipelineEngine(store=store)
        yield eng


class TestPipelineEngine:
    def test_initial_state(self, engine):
        assert engine.state == PipelineState.IDLE

    def test_initialize_project(self, engine):
        assert engine.initialize(
            name="测试小说",
            genre="玄幻",
            platform="起点",
            protagonist="林尘",
            world_setting="仙侠世界",
        )
        assert engine.state == PipelineState.PROJECT_INIT
        assert engine.project is not None
        assert engine.project.name == "测试小说"

    def test_start_planning(self, engine):
        engine.initialize("测试小说")
        assert engine.start_planning(outline="第一章：穿越\n第二章：修炼")
        assert engine.state == PipelineState.PLANNING
        assert engine.project.outline == "第一章：穿越\n第二章：修炼"

    def test_write_chapter(self, engine):
        engine.initialize("测试小说")
        engine.start_planning(outline="大纲内容")
        assert engine.write_chapter(title="第一章", content="这是第一章的内容...")
        assert engine.state == PipelineState.WRITING
        assert engine._current_chapter == 1

    def test_full_pipeline(self, engine):
        engine.initialize("测试小说")
        engine.start_planning("大纲")
        engine.write_chapter("第一章", "正文内容")
        assert engine.request_review()
        assert engine.state == PipelineState.REVIEWING

        # 审稿通过
        assert engine.approve_chapter(revisions_needed=False)
        assert engine.state == PipelineState.WRITING

        # 写第二章
        engine.write_chapter("第二章", "更多正文")
        assert engine._current_chapter == 2

    def test_review_reject_revise(self, engine):
        engine.initialize("测试小说")
        engine.start_planning("大纲")
        engine.write_chapter("第一章", "正文")
        engine.request_review()
        assert engine.approve_chapter(revisions_needed=True)
        assert engine.state == PipelineState.REVISING

        # 修改完成，重新审查
        assert engine.complete_revision()
        assert engine.state == PipelineState.REVIEWING

    def test_illegal_transition(self, engine):
        """不能直接跳过规则"""
        with pytest.raises(StateTransitionError):
            engine._sm.transition_to(PipelineState.WRITING)

    def test_write_without_outline(self, engine):
        """没有大纲不能写正文"""
        engine.initialize("测试小说")
        assert not engine.write_chapter("第一章", "正文")
        assert engine.error is not None

    def test_finish_novel(self, engine):
        engine.initialize("测试小说")
        engine.start_planning("大纲")
        engine.write_chapter("第一章", "正文")
        engine.request_review()
        engine.approve_chapter(revisions_needed=False)
        engine.write_chapter("第二章", "正文")
        engine.request_review()
        assert engine.finish_novel()
        assert engine.state == PipelineState.COMPLETED

    def test_add_character(self, engine):
        engine.initialize("测试小说")
        engine.start_planning("大纲")
        assert engine.add_character("林尘", role="主角")
        assert engine.add_character("小红", role="女主")
        assert len(engine.project.characters) == 2

    def test_add_plot_thread(self, engine):
        engine.initialize("测试小说")
        engine.start_planning("大纲")
        assert engine.add_plot_thread("revenge", "主角复仇线")
        assert len(engine.project.plot_threads) == 1

    def test_load_save_project(self, engine):
        engine.initialize("测试小说", genre="玄幻")
        engine.start_planning("大纲")
        engine.write_chapter("第一章", "正文")
        engine.write_chapter("第二章", "更多正文")

        name = engine.project.name
        engine2 = NovelPipelineEngine(store=engine.store)
        assert engine2.load_project(name)
        assert engine2.project.name == "测试小说"
        assert engine2.project.genre == "玄幻"
        assert len(engine2.project.chapters) == 2
        assert engine2.state == PipelineState.WRITING

    def test_get_state_info(self, engine):
        info = engine.get_state_info()
        assert info["current_state"] == "IDLE"
        assert info["allowed_transitions"] == ["PROJECT_INIT"]

    def test_reset(self, engine):
        engine.initialize("测试")
        assert engine.state != PipelineState.IDLE
        engine.reset()
        assert engine.state == PipelineState.IDLE
        assert engine.project is None

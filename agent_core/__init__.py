"""
agent_core — Agent 执行引擎

通过 Python 状态机强制执行创作管线流程，避免纯 Prompt 工程带来的
"LLM 不遵守约束" 问题。所有管线状态转换由代码控制，LLM 只能通过
预留的 hook 接口与引擎交互。
"""

from .engine import NovelPipelineEngine, PipelineState
from .project import Project, ProjectStore
from .state_machine import StateMachine, StateTransitionError

__all__ = [
    "NovelPipelineEngine",
    "PipelineState",
    "Project",
    "ProjectStore",
    "StateMachine",
    "StateTransitionError",
]

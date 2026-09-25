"""
state_machine.py — 通用有限状态机

定义状态、合法转换和守卫条件。任何不符合预设转换规则的状态变化都会被拒绝。
"""

from __future__ import annotations

from enum import Enum
from collections.abc import Callable
from typing import Any


class StateTransitionError(Exception):
    """非法状态转换异常"""


class StateMachine:
    """通用有限状态机

    用法：
        sm = StateMachine()
        sm.add_transition(StateA, StateB)
        sm.current = StateA
        sm.transition_to(StateB)  # OK
        sm.transition_to(StateC)  # StateTransitionError
    """

    def __init__(self, initial_state: Enum | None = None):
        self._transitions: dict[Enum, set[Enum]] = {}
        self._guards: dict[tuple[Enum, Enum], Callable[[], bool]] = {}
        self._on_entry: dict[Enum, list[Callable[[], None]]] = {}
        self._on_exit: dict[Enum, list[Callable[[], None]]] = {}
        self._current: Enum | None = initial_state

    @property
    def current(self) -> Enum | None:
        return self._current

    @current.setter
    def current(self, state: Enum) -> None:
        """直接设置状态（仅用于初始化，不触发 hook）"""
        self._current = state

    def add_transition(self, from_state: Enum, to_state: Enum) -> None:
        if from_state not in self._transitions:
            self._transitions[from_state] = set()
        self._transitions[from_state].add(to_state)

    def add_guard(self, from_state: Enum, to_state: Enum, guard_fn: Callable[[], bool]) -> None:
        self._guards[(from_state, to_state)] = guard_fn

    def add_on_entry(self, state: Enum, fn: Callable[[], None]) -> None:
        if state not in self._on_entry:
            self._on_entry[state] = []
        self._on_entry[state].append(fn)

    def add_on_exit(self, state: Enum, fn: Callable[[], None]) -> None:
        if state not in self._on_exit:
            self._on_exit[state] = []
        self._on_exit[state].append(fn)

    def can_transition_to(self, state: Enum) -> bool:
        if self._current is None:
            return True
        allowed = self._transitions.get(self._current, set())
        if state not in allowed:
            return False
        guard = self._guards.get((self._current, state))
        if guard is not None and not guard():
            return False
        return True

    def transition_to(self, state: Enum) -> None:
        if self._current is not None:
            allowed = self._transitions.get(self._current, set())
            if state not in allowed:
                raise StateTransitionError(
                    f"不允许从 {self._current} 转换到 {state}"
                )
            guard = self._guards.get((self._current, state))
            if guard is not None and not guard():
                raise StateTransitionError(
                    f"守卫条件阻止了从 {self._current} 到 {state} 的转换"
                )
            # 触发 exit hooks
            for fn in self._on_exit.get(self._current, []):
                fn()

        old = self._current
        self._current = state

        # 触发 entry hooks
        for fn in self._on_entry.get(state, []):
            fn()

    def get_allowed_transitions(self) -> list[Enum]:
        if self._current is None:
            return []
        return list(self._transitions.get(self._current, set()))

    def reset(self, state: Enum) -> None:
        self._current = state

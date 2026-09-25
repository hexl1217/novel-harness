"""runtime state 落盘：把跨会话必须存活的运行时状态写进文件。

为什么要这个模块
----------------
`.harness/rules/subagent-runtime.md` 定义了挂起恢复（`resume_id` + 栈式嵌套恢复）、
`.harness/knowledge/pack-recommendation.md` 定义了开书推荐状态机（S0–S5 与
`selected_topic` / `selected_platform` / `selected_pack`）。这些状态变量此前
**只存在于对话上下文里**——全仓库有 61 处引用，却没有任何持久化载体。会话一断、
上下文一压缩，恢复点就没了，于是整套「挂起恢复」机制悬空。

本模块给这些变量一个真正的落盘位置：

    .harness/state/runtime.json

用法（CLI）：

    python -m agent_core.state show
    python -m agent_core.state show --json
    python -m agent_core.state set selected_topic topic-xuanhuan
    python -m agent_core.state unset selected_topic
    python -m agent_core.state push-resume R3 "查知识包" --payload task="补题材包"
    python -m agent_core.state pop-resume
    python -m agent_core.state clear

`--file` 是全局选项，必须放在子命令**之前**，用于覆盖状态文件位置（测试与 CI 用）。

设计取舍
--------
- **单文件**而非按项目分文件：开书状态机（S0–S5）发生在「项目」存在之前，
  挂起恢复栈也是会话级的，按项目切分反而找不到归属。
- **未知键不丢**：`set` 只做合并，不做白名单校验。规则演进时新增变量不需要改代码。
- **写入原子化**：先写 `.tmp` 再 `replace`，避免半截 JSON 把状态搞坏。
- **损坏不静默**：解析失败时把原文件备份成 `runtime.corrupt.json` 再重建，
  不假装什么都没发生。
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_FILE = PROJECT_ROOT / ".harness" / "state" / "runtime.json"

# 与规则文件对应的已知字段。仅用于 `show` 排序与文档提示，
# 不构成白名单——未知键同样会被持久化。
KNOWN_FIELDS = (
    "stage",                 # 开书状态机阶段 S0–S5（总编Agent.md）
    "current_project",       # 当前项目（与 .harness/current-project.md 互为索引）
    "selected_topic",        # 已锁定题材（S3）
    "selected_platform",     # 已锁定平台（S3）
    "selected_pack",         # 已锁定知识包（S3）
    "next_action",           # 下一步动作
    "recommendation_state",  # 推荐态（pack-recommendation.md）
    "setting_session_id",    # 设定会话 id
    "accepted_result",       # 用户已接受的产出
)


class StateStore:
    """`.harness/state/runtime.json` 的读写。

    Args:
        path: 状态文件位置。默认 `.harness/state/runtime.json`；
              测试必须传入临时路径，避免污染仓库真实状态。
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_STATE_FILE

    # ---------- 基础读写 ----------

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"version": 1, "updated_at": "", "resume_stack": []}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine()
            return self._empty()
        if not isinstance(data, dict):
            self._quarantine()
            return self._empty()

        state = self._empty()
        state.update(data)
        stack = state.get("resume_stack")
        state["resume_stack"] = [x for x in stack if isinstance(x, dict)] if isinstance(stack, list) else []
        return state

    def save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def _quarantine(self) -> None:
        """把无法解析的状态文件挪到一边，便于事后排查。"""
        try:
            backup = self.path.with_name(self.path.stem + ".corrupt.json")
            backup.write_text(self.path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        except OSError:
            pass

    # ---------- 键值操作 ----------

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def update(self, **fields: Any) -> dict[str, Any]:
        """合并写入若干字段并返回新状态。未知键原样保留。"""
        state = self.load()
        state.update(fields)
        self.save(state)
        return state

    def unset(self, key: str) -> dict[str, Any]:
        state = self.load()
        state.pop(key, None)
        self.save(state)
        return state

    def clear(self) -> dict[str, Any]:
        state = self._empty()
        self.save(state)
        return state

    # ---------- 挂起恢复栈 ----------
    # subagent-runtime.md：A 挂起 → B 挂起 → C；C 完恢复 B，B 完恢复 A。禁止跳层。

    def push_resume(self, resume_id: str, task: str = "", **payload: Any) -> dict[str, Any]:
        state = self.load()
        state["resume_stack"].append({
            "resume_id": resume_id,
            "task": task,
            "payload": payload,
            "pushed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        self.save(state)
        return state

    def peek_resume(self) -> dict[str, Any] | None:
        """查看栈顶恢复点，不弹出。"""
        stack = self.load()["resume_stack"]
        return stack[-1] if stack else None

    def pop_resume(self) -> dict[str, Any] | None:
        """弹出栈顶恢复点。栈空返回 None。"""
        state = self.load()
        if not state["resume_stack"]:
            return None
        entry = state["resume_stack"].pop()
        self.save(state)
        return entry

    def resume_depth(self) -> int:
        return len(self.load()["resume_stack"])


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="novel-harness 运行时状态落盘")
    parser.add_argument("--file", default=None, help="覆盖状态文件位置")
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="显示当前状态")
    p_show.add_argument("--json", action="store_true")

    p_set = sub.add_parser("set", help="写入一个字段")
    p_set.add_argument("key")
    p_set.add_argument("value")

    p_unset = sub.add_parser("unset", help="删除一个字段")
    p_unset.add_argument("key")

    p_push = sub.add_parser("push-resume", help="压入恢复点")
    p_push.add_argument("resume_id")
    p_push.add_argument("task", nargs="?", default="")
    p_push.add_argument("--payload", action="append", default=[], metavar="K=V")

    sub.add_parser("pop-resume", help="弹出栈顶恢复点")
    sub.add_parser("clear", help="清空状态（保留版本号）")

    args = parser.parse_args(argv)
    store = StateStore(args.file)

    if args.command == "show":
        state = store.load()
        if args.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
        else:
            print(f"状态文件：{store.path}")
            print(f"更新时间：{state.get('updated_at') or '(未写过)'}")
            for key in KNOWN_FIELDS:
                if key in state:
                    print(f"  {key} = {state[key]}")
            extra = [k for k in state if k not in KNOWN_FIELDS
                     and k not in ("version", "updated_at", "resume_stack")]
            for key in extra:
                print(f"  {key} = {state[key]}")
            stack = state["resume_stack"]
            print(f"  挂起恢复栈（{len(stack)} 层，LIFO）:")
            for depth, entry in enumerate(reversed(stack), start=1):
                print(f"    {depth}. {entry.get('resume_id')} — {entry.get('task') or '(无描述)'}")
        return 0

    if args.command == "set":
        store.update(**{args.key: args.value})
        print(f"已写入 {args.key} = {args.value}")
        return 0

    if args.command == "unset":
        store.unset(args.key)
        print(f"已删除 {args.key}")
        return 0

    if args.command == "push-resume":
        payload: dict[str, str] = {}
        for item in args.payload:
            if "=" in item:
                key, _, value = item.partition("=")
                payload[key.strip()] = value.strip()
        store.push_resume(args.resume_id, args.task, **payload)
        print(f"已压入恢复点 {args.resume_id}（当前栈深 {store.resume_depth()}）")
        return 0

    if args.command == "pop-resume":
        entry = store.pop_resume()
        if entry is None:
            print("恢复栈为空，无可弹出项。", file=sys.stderr)
            return 1
        print(f"已恢复：{entry.get('resume_id')} — {entry.get('task') or '(无描述)'}")
        if entry.get("payload"):
            print(f"  载荷：{json.dumps(entry['payload'], ensure_ascii=False)}")
        print(f"剩余栈深：{store.resume_depth()}")
        return 0

    if args.command == "clear":
        store.clear()
        print("状态已清空。")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

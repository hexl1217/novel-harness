"""state.py 的单元测试：落盘、原子写、损坏隔离、挂起恢复栈的 LIFO 语义。"""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.state import StateStore, main  # noqa: E402


def make_store(tmp_path) -> StateStore:
    return StateStore(tmp_path / "state" / "runtime.json")


def test_missing_file_returns_defaults(tmp_path):
    state = make_store(tmp_path).load()
    assert state["version"] == 1
    assert state["resume_stack"] == []


def test_update_persists_across_instances(tmp_path):
    store = make_store(tmp_path)
    store.update(selected_topic="topic-xuanhuan", stage="S3")

    reloaded = make_store(tmp_path).load()
    assert reloaded["selected_topic"] == "topic-xuanhuan"
    assert reloaded["stage"] == "S3"
    assert reloaded["updated_at"]


def test_update_merges_and_keeps_unknown_keys(tmp_path):
    store = make_store(tmp_path)
    store.update(custom_flag="keep-me")
    store.update(stage="S4")

    state = store.load()
    assert state["custom_flag"] == "keep-me"
    assert state["stage"] == "S4"


def test_unset_removes_only_that_key(tmp_path):
    store = make_store(tmp_path)
    store.update(selected_topic="a", selected_pack="b")
    store.unset("selected_topic")

    state = store.load()
    assert "selected_topic" not in state
    assert state["selected_pack"] == "b"


def test_resume_stack_is_lifo(tmp_path):
    """subagent-runtime：A 挂起 → B 挂起 → C，C 完恢复 B，B 完恢复 A。"""
    store = make_store(tmp_path)
    store.push_resume("R1", "原任务")
    store.push_resume("R2", "查知识包")
    store.push_resume("R3", "确认题材")

    assert store.resume_depth() == 3
    assert store.peek_resume()["resume_id"] == "R3"
    assert store.pop_resume()["resume_id"] == "R3"
    assert store.pop_resume()["resume_id"] == "R2"
    assert store.pop_resume()["resume_id"] == "R1"
    assert store.resume_depth() == 0


def test_pop_on_empty_returns_none(tmp_path):
    assert make_store(tmp_path).pop_resume() is None


def test_resume_payload_roundtrip(tmp_path):
    store = make_store(tmp_path)
    store.push_resume("R9", "补题材包", pack_id="topic-mystery", scope="本轮")

    entry = store.pop_resume()
    assert entry["payload"] == {"pack_id": "topic-mystery", "scope": "本轮"}


def test_corrupt_file_is_quarantined_not_silently_dropped(tmp_path):
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{ 这不是合法 JSON", encoding="utf-8")

    state = store.load()
    assert state["resume_stack"] == []

    backup = store.path.with_name(store.path.stem + ".corrupt.json")
    assert backup.exists()
    assert "这不是合法 JSON" in backup.read_text(encoding="utf-8")


def test_non_dict_payload_is_quarantined(tmp_path):
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("[1, 2, 3]", encoding="utf-8")

    assert store.load()["resume_stack"] == []
    assert store.path.with_name(store.path.stem + ".corrupt.json").exists()


def test_resume_stack_ignores_non_dict_entries(tmp_path):
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"resume_stack": ["脏数据", {"resume_id": "R1"}]}),
                          encoding="utf-8")

    assert store.resume_depth() == 1


def test_write_is_atomic_and_leaves_no_tmp(tmp_path):
    store = make_store(tmp_path)
    store.update(stage="S1")

    leftovers = list(store.path.parent.glob("*.tmp"))
    assert leftovers == []


def test_clear_resets_but_keeps_version(tmp_path):
    store = make_store(tmp_path)
    store.update(selected_topic="a")
    store.push_resume("R1")

    state = store.clear()
    assert state["version"] == 1
    assert state["resume_stack"] == []
    assert "selected_topic" not in state


def test_cli_set_and_show(tmp_path, capsys):
    target = str(tmp_path / "runtime.json")
    assert main(["--file", target, "set", "stage", "S2"]) == 0
    capsys.readouterr()  # 丢弃 set 的输出，否则会混进下面的 JSON

    assert main(["--file", target, "show", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "S2"


def test_cli_push_and_pop_resume(tmp_path, capsys):
    target = str(tmp_path / "runtime.json")
    assert main(["--file", target, "push-resume", "R7", "查包", "--payload", "pack=topic-x"]) == 0
    capsys.readouterr()

    assert main(["--file", target, "show"]) == 0
    assert "R7" in capsys.readouterr().out

    assert main(["--file", target, "pop-resume"]) == 0
    out = capsys.readouterr().out
    assert "R7" in out and "topic-x" in out


def test_cli_pop_on_empty_returns_one(tmp_path, capsys):
    target = str(tmp_path / "runtime.json")
    assert main(["--file", target, "pop-resume"]) == 1
    capsys.readouterr()

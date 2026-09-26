"""check_draft 的单元测试：断言每条检查项都能命中，且保护区域不误伤。"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.check_draft import (  # noqa: E402
    check_path,
    check_text,
    count_cjk,
    main,
)


def test_count_cjk_counts_only_hanzi():
    assert count_cjk("他说：hello 世界") == 4


def test_t0_pattern_in_narration_is_error():
    issues = check_text("他眨了下眼。不是坏了，是快废了。")
    assert any(item.level == "error" and "T0" in item.rule for item in issues)


def test_t0_pattern_in_dialogue_is_info():
    issues = check_text("「不是他，是我。」")
    assert any(item.level == "info" and "T0" in item.rule for item in issues)
    assert not any(item.level == "error" for item in issues)


def test_banned_fingerprint_word_is_error():
    issues = check_text("这套打法需要赋能。")
    assert any(item.level == "error" and "赋能" in item.message for item in issues)


def test_common_fingerprint_word_is_warn():
    issues = check_text("他复盘了整件事。")
    assert any(item.level == "warn" and "复盘" in item.message for item in issues)


def test_ai_filler_phrase_is_warn():
    issues = check_text("综上所述，他决定先走。")
    assert any("废话短语" in item.rule for item in issues)


def test_verb_noun_style_is_warn():
    issues = check_text("他进行了一次搜索。")
    assert any("进行病" in item.rule for item in issues)


def test_identity_tag_is_warn():
    issues = check_text("作为一名社区工作者的他，先开了口。")
    assert any("身份重复标签" in item.rule for item in issues)


def test_overlong_paragraph_is_warn():
    issues = check_text("他" * 70)
    assert any("单段" in item.message for item in issues)


def test_overlong_sentence_is_warn():
    sentence = "他" * 50 + "。"
    issues = check_text(sentence)
    assert any("单句" in item.message for item in issues)


def test_consecutive_transition_paragraphs_is_warn():
    issues = check_text("不过他没说话。\n\n但是他又想开口。")
    assert any("过渡词过度" in item.rule for item in issues)


def test_formula_line_in_narration_is_error():
    """反馈 2026-09-24：算式独立成行顶替人物动作，属四类成因之一，判 error。"""
    issues = check_text("他算了算。\n41.64 + 406.26 + 279.48 = 727.38")
    assert any(item.level == "error" and "数字出场分层" in item.rule for item in issues)


def test_formula_on_carrier_is_exempt():
    """同一反馈「保留不动」清单：写在纸/白板上的算式由载体承载，不算生硬。"""
    issues = check_text("老谭掏出铅笔，在纸上写：\n九十四天 × 二百元 = 一万八千八")
    assert not [item for item in issues if "数字出场分层" in item.rule]

    board = check_text("白板上写着：41.64 + 406.26 + 279.48 = 727.38")
    assert not [item for item in board if "数字出场分层" in item.rule]


def test_arabic_formula_in_dialogue_is_error():
    """规则要求人物嘴上一律用汉字；DIALOGUE_FORMULA_PATTERN 负责嵌在句中的情形。"""
    issues = check_text("他张嘴就来：「12+8=20，错不了。」")
    assert any(item.level == "error" and "对白" in item.message for item in issues)


def test_dialogue_wins_over_carrier():
    """同段既有载体词又有对白算式时，对白优先判违规。"""
    issues = check_text("白板上抄着数，他念：「12+8=20」。")
    assert any(item.level == "error" and "对白" in item.message for item in issues)


def test_system_panel_is_masked():
    issues = check_text("【生命值：23/32】")
    assert not [item for item in issues if item.level == "error"]


def test_code_fence_is_masked():
    issues = check_text("```\n不是坏了，是快废了。\n```")
    assert not [item for item in issues if "T0" in item.rule]


def test_word_target_deviation_is_warn():
    issues = check_text("他" * 100, target_words=500)
    assert any("字数门禁" in item.rule for item in issues)


def test_path_convention():
    assert check_path(Path("projects/迷雾民宿/正文/第1章.md")) == []

    bad = check_path(Path("projects/迷雾民宿/ch0001.md"))
    assert bad and bad[0].level == "error"


def test_cli_returns_nonzero_on_error(tmp_path, capsys):
    chapter = tmp_path / "projects" / "demo" / "正文" / "第1章.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("不是坏了，是快废了。", encoding="utf-8")
    code = main([str(chapter), "--json"])
    capsys.readouterr()
    assert code == 1


def test_cli_clean_text_returns_zero(tmp_path, capsys):
    chapter = tmp_path / "projects" / "demo" / "正文" / "第1章.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("他把杯子放下。\n\n窗外有风。", encoding="utf-8")
    code = main([str(tmp_path / "projects" / "demo"), "--json"])
    capsys.readouterr()
    assert code == 0


def test_cli_allow_empty_returns_zero(tmp_path, capsys):
    """CI 场景：projects/ 为空时应通过而不是失败。"""
    code = main([str(tmp_path / "empty"), "--allow-empty"])
    capsys.readouterr()
    assert code == 0


def test_cli_without_allow_empty_fails_when_no_files(tmp_path, capsys):
    code = main([str(tmp_path / "empty")])
    capsys.readouterr()
    assert code == 1


def test_directory_without_drafts_is_skipped_not_misread(tmp_path, capsys):
    """目录里只有非正文 md 时，不得把 项目档案.md 当正文校验。"""
    project = tmp_path / "projects" / "demo"
    project.mkdir(parents=True)
    (project / "项目档案.md").write_text("不是坏了，是快废了。", encoding="utf-8")
    code = main([str(project), "--allow-empty"])
    capsys.readouterr()
    assert code == 0

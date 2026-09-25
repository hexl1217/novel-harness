"""draft_metrics 回归测试。

重点不是覆盖率，而是**判别性**：同样的剧情、同样的字数，
「AI 腔」样本必须被大量标出，「人写」样本必须一条不报。

这条判别性断言是本次改动的核心价值 —— 如果它失效，说明指标退化成
「有数字但分不出好坏」，比没有指标更糟（会给出虚假的安心感）。
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_core.draft_metrics import (  # noqa: E402
    THRESHOLDS,
    _longest_uniform_run,
    analyze,
    findings,
    main,
    split_sentences,
    visible_len,
)

FIXTURES = Path(__file__).parent / "fixtures"
AI_SAMPLE = FIXTURES / "draft_ai_flavor.md"
HUMAN_SAMPLE = FIXTURES / "draft_human.md"

# 加法侧（缺少）——本次改动的主目标，必须一个不少地全部命中
EXPECTED_MISSING = {
    "longest_uniform_run",
    "very_short_count",
    "longest_uniform_paragraph_run",
    "longest_uniform_dialogue_run",
    "sensory_channels",
    "colloquial_density",
    "reduplication_count",
}
# 减法侧（出现）——check_draft 未覆盖的那几条
EXPECTED_PRESENT = {
    "summary_ending_count",
    "action_chain_count",
    "causal_chain_count",
    "emotion_label_count",
    "time_adverb_count",
    "listing_paragraph_count",
    "precise_unit_count",
}


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ai():
    return analyze(_load(AI_SAMPLE))


@pytest.fixture(scope="module")
def human():
    return analyze(_load(HUMAN_SAMPLE))


# --- 基础工具 ---------------------------------------------------------------

class TestSentenceSplitting:
    def test_closing_quote_is_merged_into_previous_sentence(self):
        """「你好。」 的收尾引号不能被切到下一句去。"""
        sents = split_sentences("「你好。」他走了。")
        assert sents == ["「你好。」他走了。"]

    def test_full_width_quote_also_merged(self):
        sents = split_sentences("他说：“走吧。”然后停下。")
        assert len(sents) == 1

    def test_visible_len_ignores_whitespace(self):
        assert visible_len("  他 走 了 。 ") == 4
        assert visible_len("") == 0


class TestUniformRun:
    """_longest_uniform_run 的判据是**整串相对跨度**，不是两两相邻差。

    这是修掉「28→21→16 被误判成均匀」的关键：
    旧实现（两两相邻差）下 28/21/16 会被算成 3 句均匀串，导致人写样本被误报。
    """

    @pytest.mark.parametrize("values,expected", [
        ([29, 25, 28], 3),          # 平坦：整串跨度 15%
        ([20, 21, 20, 19, 22], 5),  # 长平坦
        ([10, 10, 10, 10, 10], 5),  # 全同
        ([4, 5, 4, 5], 4),          # 短句平坦也算
        ([28, 21, 16], 1),          # 递降：每步 25%，但整串跨度 43% —— 不是均匀
        ([30, 25, 20, 16], 2),      # 两两相近但整体递降
        ([8, 6, 4, 3], 1),          # 短句递降
        ([5, 40, 6, 38], 1),        # 悬殊
        ([], 0),
        ([12], 1),
    ])
    def test_run_length(self, values, expected):
        assert _longest_uniform_run(values) == expected

    def test_threshold_makes_flat_run_a_violation(self):
        """4.1 门禁「相邻三句的长度不要相近」→ 3 句平坦串必须超阈值。"""
        assert _longest_uniform_run([29, 25, 28]) > THRESHOLDS["uniform_run_max"]

    def test_would_have_failed_under_old_pairwise_definition(self):
        """证明「递降不算均匀」这条断言不是空转。

        旧实现按两两相邻差判定：28→21 差 7（≤ 0.25×28），21→16 差 5（≤ 0.25×21），
        于是 28/21/16 被判成 3 句均匀串 —— 人写样本里恰好有这一段，会被误报。
        这里把旧实现原样写出来断言它确实误报，从而保证新实现的这条修正是有效的。
        """

        def old_pairwise(values, tol=0.25):
            best = cur = 1
            for i in range(1, len(values)):
                a, b = values[i - 1], values[i]
                if abs(a - b) <= max(1, tol * max(a, b)):
                    cur += 1
                    best = max(best, cur)
                else:
                    cur = 1
            return best

        descending = [28, 21, 16]
        assert old_pairwise(descending) == 3            # 旧实现：误报为均匀
        assert _longest_uniform_run(descending) == 1    # 新实现：识别为递降，不报


class TestPruningEquivalence:
    """剪枝版必须与朴素 O(n²) 实现**逐位等价**。

    剪枝是性能手段，绝不能换来语义漂移；这里用随机数据对拍兜底。
    """

    @staticmethod
    def _naive(values):
        """朴素参考实现：原样保留剪枝前的写法，作为唯一真值。"""
        n = len(values)
        if n == 0:
            return 0
        best = 1
        for i in range(n):
            lo = hi = values[i]
            total = values[i]
            for j in range(i + 1, n):
                v = values[j]
                lo = min(lo, v)
                hi = max(hi, v)
                total += v
                mean = total / (j - i + 1)
                if mean <= 0 or (hi - lo) > 0.25 * mean:
                    continue
                best = max(best, j - i + 1)
        return best

    @pytest.mark.parametrize("seed", range(12))
    def test_matches_naive_on_random_data(self, seed):
        rng = random.Random(seed)
        for _ in range(8):
            n = rng.randint(0, 60)
            lo = rng.choice([0, 1, 3, 10, 25])
            span = rng.choice([1, 2, 5, 40, 200])
            values = [rng.randint(lo, lo + span) for _ in range(n)]
            assert _longest_uniform_run(values) == self._naive(values), values

    def test_matches_naive_on_structured_data(self):
        """刻意构造几种能把「continue 改 break」逼出错的数据形态。"""
        cases = [
            [20] * 40,                                   # 全同：答案就是全长
            [20] * 30 + [25, 20, 26, 20, 24],            # 长均匀段 + 抖动尾巴
            [8, 9, 8, 9] * 15,                           # 双值交替
            [10, 40, 10, 40, 10],                        # 剧烈抖动
            list(range(10, 60)) + [10] * 5,              # 单调递增 + 均匀尾
            [100, 99, 101, 98, 102, 97],                 # 窄带内波动
        ]
        for values in cases:
            assert _longest_uniform_run(values) == self._naive(values), values

    def test_pruning_keeps_the_two_calibration_verdicts(self):
        """两个判别样本上的结论不能因剪枝而变。"""
        assert _longest_uniform_run([5] * 9) == 9
        assert _longest_uniform_run([28, 21, 16]) == 1

    def test_long_uniform_run_is_found_in_linear_time(self):
        """回归上一轮探针暴露的 O(n²)：整本规模（1.2 万句）必须秒回。"""
        values = [20 + (i % 3) for i in range(12000)]   # 窄带波动 → 全串都算均匀
        start = time.perf_counter()
        got = _longest_uniform_run(values)
        elapsed = time.perf_counter() - start
        assert got == 12000
        assert elapsed < 1.0, f"剪枝失效，耗时 {elapsed:.2f}s"


# --- 核心：判别性 -----------------------------------------------------------

class TestSampleDiscrimination:
    """AI 腔样本 vs 人写样本，同一剧情同一篇幅。"""

    def test_ai_sample_is_flagged_on_all_expected_metrics(self, ai):
        got_missing = {f.metric for f in findings(ai) if f.direction == "缺少"}
        got_present = {f.metric for f in findings(ai) if f.direction == "出现"}
        assert got_missing == EXPECTED_MISSING
        assert got_present == EXPECTED_PRESENT

    def test_ai_sample_has_no_info_level_noise_on_warn(self, ai):
        warns = [f for f in findings(ai) if f.level == "warn"]
        assert len(warns) == len(EXPECTED_MISSING | EXPECTED_PRESENT) - 1  # precise_unit 是 info

    def test_human_sample_is_completely_clean(self, human):
        """人写样本必须一条都不报 —— 这是不误伤的上界。"""
        assert findings(human) == []

    # --- 逐指标对照：AI 在每条上都更差 ---

    def test_rhythm_metrics(self, ai, human):
        assert ai.longest_uniform_run > human.longest_uniform_run
        assert ai.longest_uniform_paragraph_run > human.longest_uniform_paragraph_run
        assert ai.longest_uniform_dialogue_run > human.longest_uniform_dialogue_run
        assert ai.very_short_count < human.very_short_count

    def test_sensory_coverage(self, ai, human):
        assert ai.sensory_channels == ["视觉"]
        assert len([c for c in human.sensory_channels if c != "视觉"]) >= 3

    def test_voice_metrics(self, ai, human):
        assert ai.colloquial_density == 0
        assert ai.reduplication_count == 0
        assert ai.ba_sentence_count == 0
        assert ai.pause_paragraph_count == 0
        assert human.colloquial_density > THRESHOLDS["colloquial_density_min"]
        assert human.reduplication_count >= THRESHOLDS["reduplication_min"]
        assert human.ba_sentence_count > 0
        assert human.pause_paragraph_count > 0

    def test_subtractive_metrics(self, ai, human):
        assert ai.action_chain_count > human.action_chain_count
        assert ai.causal_chain_count > human.causal_chain_count
        assert ai.time_adverb_count > human.time_adverb_count
        assert ai.emotion_label_count > human.emotion_label_count
        assert ai.summary_ending_count > human.summary_ending_count
        assert ai.listing_paragraph_count > human.listing_paragraph_count
        assert ai.precise_unit_count > human.precise_unit_count

    def test_two_tools_are_complementary_not_duplicated(self, ai, human):
        """draft_metrics 抓的应当是 check_draft 抓不到的那一层。

        check_draft 抓「出现了禁止的东西」（判定式短句、段落超长…），
        draft_metrics 抓「缺少了该有的东西」（节奏、感官、口气…）。
        这里断言后者的核心指标在前者的词表里根本不存在。
        """
        from agent_core import check_draft

        check_draft_source = Path(check_draft.__file__).read_text(encoding="utf-8")
        for metric_marker in ("longest_uniform_run", "colloquial_density",
                              "reduplication_count", "sensory_channels"):
            assert metric_marker not in check_draft_source


# --- 每条结论都必须有规则出处（审稿Agent 硬性要求） ------------------------

class TestRuleProvenance:
    @pytest.mark.parametrize("sample", [AI_SAMPLE, HUMAN_SAMPLE])
    def test_every_finding_cites_a_rule(self, sample):
        for f in findings(analyze(_load(sample))):
            assert f.rule.strip(), f"finding {f.metric} 缺规则出处"
            assert f.rule != "—", f"finding {f.metric} 只写了占位符"

    def test_all_thresholds_are_documented(self):
        """阈值表里不该有孤立项：每一项都要被 findings/analyze 真正用到。"""
        src = Path(__file__).resolve().parents[1] / "draft_metrics.py"
        source = src.read_text(encoding="utf-8")
        for key in THRESHOLDS:
            assert f'"{key}"' in source.replace("THRESHOLDS = {", "", 1) or key in source
            assert source.count(f'THRESHOLDS["{key}"]') >= 1, f"阈值 {key} 声明了却没用"


# --- 退化输入 ---------------------------------------------------------------

class TestDegenerateInput:
    def test_empty_text_does_not_crash(self):
        m = analyze("")
        assert m.cjk == 0
        assert m.sentence_count == 0
        assert m.longest_uniform_run == 0
        assert m.sensory_channels == []

    def test_whitespace_only(self):
        m = analyze("   \n\n \t ")
        assert m.paragraph_count == 0
        assert m.sentence_count == 0

    def test_very_short_text_gets_sample_size_hint(self):
        items = findings(analyze("他走了。"))
        assert any(f.metric == "sample" for f in items)

    def test_system_panel_is_masked_and_not_counted(self, tmp_path):
        """【】面板不该被当成正文参与节奏统计。"""
        text = "他走了。\n【系统提示】恭喜获得三把钥匙、两张地图。\n他停下。\n"
        m = analyze(text)
        assert "他走了" in text
        # 面板被掩码成空白，不该贡献「清单式罗列」
        assert m.listing_paragraph_count == 0


# --- CLI --------------------------------------------------------------------

class TestCli:
    def test_clean_sample_exits_zero(self, capsys):
        assert main([str(HUMAN_SAMPLE)]) == 0

    def test_strict_flags_warn_sample(self, capsys):
        assert main([str(AI_SAMPLE), "--strict"]) == 1

    def test_json_output_is_parseable(self, capsys):
        import json

        main([str(AI_SAMPLE), "--json"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["path"].endswith("draft_ai_flavor.md")
        assert payload["metrics"]["cjk"] > 0
        assert len(payload["findings"]) >= 10

"""正文「人味 / 节奏」画像：把 `.harness` 规则里**加法侧**的条款落成可计算指标。

背景
----
`check_draft.py` 覆盖的全是「不该出现什么」（禁止句、指纹词、长度上限、标点…）。
但一章正文读起来不像人写的，通常不是「多了什么」，而是「缺了什么」——
缺感官、缺废话、缺长短句变化、缺重复强调、缺停顿空间。

这些条款在 `.harness` 里**本来就写着明确的「门禁」**，只是从来没有被机器化：

- `.harness/skills/human-linguistics/rules/句式节奏档案.md`
  4.1 长短句交替 / 4.2 断句留白 / 4.3 语气随情绪 / 4.4 把字句 / 4.5 重复强调 / 4.6 心理代偿
- `.harness/skills/human-linguistics/rules/语病诊断手册.md`
  2.3 动作过度完整 / 2.4 情感标签化 / 2.5 因果链过度完整 / 2.6 全方位观察
  2.7 每段必推进 / 2.8 标准答案式结尾 / 2.9 多余时间副词 / 2.11 重复强调缺失
- `.harness/agents/写作Agent.md`
  场景三维度「视觉之外**至少**补触觉、听觉、嗅觉或身体细节」；Step 4「通篇一问一答」检测
- `.harness/skills/human-linguistics/SKILL.md`
  原则 1「人写东西是有废话的」/ 原则 2「人不做多余的数学」

与 `check_draft` 的分工
-----------------------
- `check_draft`   → 减法项，含 `error` 级，是**硬门禁**（不通过就不能交稿）
- `draft_metrics` → 加法项（缺失检测）+ `check_draft` 未覆盖的少数减法项，
  只有 `warn` / `info`，定位是**画像与改进提示**，不是否决

阈值
----
每条阈值对齐对应规则的「门禁」原文，不自行发明标准。集中登记在 `THRESHOLDS`，
便于后续用真实成品稿校准。**当前值为规则推导 + 对照样本校准，并非成品稿统计。**

用法
----
    python -m agent_core.draft_metrics <文件或目录>... [--json] [--strict]

目录输入会递归查找 `正文/*.md`。
退出码：0 = 无 warn；1 = 存在 warn（仅 `--strict` 时）。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agent_core.check_draft import collect_files, count_cjk, mask_text

# --- 阈值表（对齐各规则「门禁」原文） ---------------------------------------

THRESHOLDS = {
    # 句式节奏档案 4.1「相邻三句的长度不要相近」+「极短，强调」
    "uniform_run_max": 2,               # 长度相近串超过 2 句即违规
    "very_short_sentence_min": 1,       # 至少要有极短句（<=5 字）
    # writing-execution-map「不连续堆同长度短段」
    "uniform_paragraph_run_max": 3,
    # 写作Agent Step 4「通篇一问一答」
    "uniform_dialogue_run_max": 4,      # 连续 N 轮长度相近的对话即视为问答说明书
    # 写作Agent 场景三维度：视觉之外至少一个非视觉通道
    "narrative_nonvisual_min": 1,
    # 原则 1「人写东西是有废话的」+ 4.6 心理代偿
    "colloquial_density_min": 1.0,      # 每千字口语标记数
    # 语病诊断手册 2.11「全文没有一个词是重复的 → 违规」
    "reduplication_min": 1,
    # 语病诊断手册 2.8「段尾就是段尾，不需要盖章确认」
    "summary_ending_tolerance": 1,
    # 语病诊断手册 2.3 / 2.5 / 2.9：单章出现次数容忍上限
    "action_chain_tolerance": 2,
    "causal_chain_tolerance": 2,
    "time_adverb_tolerance": 1,
    # 语病诊断手册 2.4「能写身体反应就不要写心理感受」
    "emotion_label_tolerance": 1,
    # 语病诊断手册 2.6「环境描写只写角色当前会注意到的东西」
    "listing_items_max": 2,
    # 原则 2「人不做多余的数学」
    "precise_unit_tolerance": 2,
    # 语病诊断手册 2.7「在紧张的段落之间插入一段什么也没发生的文字」
    "pause_paragraph_min": 1,
    "pause_check_min_cjk": 1200,
}

# 仅报告、不作门禁的观测值：规则原文给的是「相邻三句不要相近」这类**串**判据，
# 不是方差判据，所以 CV 类指标只用于人工读报告，不参与告警（避免发明标准）。
REPORT_ONLY_METRICS = ("sentence_cv", "paragraph_cv", "short_sentence_ratio", "dialogue_line_ratio")

# --- 词表（全部取自规则文件的示例与正文） -----------------------------------

# 句式节奏档案 4.6 心理代偿 + 原则 1 真人废话 + 4.3 语气随情绪
COLLOQUIAL_MARKERS = (
    "呢", "吧", "嘛", "啊", "呀", "哦", "噢", "唉", "哎", "嗯", "咦", "诶", "哈",
    "咋", "甭", "挺", "倒是", "其实", "反正", "好歹", "硬是", "偏要", "这回", "这下",
    "心里头", "心头", "那点", "一下子", "老半天", "半天", "一会儿", "什么的", "之类",
    "似的", "大概", "差不多", "谁知道", "怎么着", "说白了",
)

# 写作Agent 场景三维度「感知」：视觉之外的通道
SENSORY_LEXICON = {
    "听觉": (
        "听到", "听见", "声音", "声响", "响声", "静", "吵", "轰", "叮", "咚",
        "哗", "吱", "嗡", "喘", "呼吸声", "咔", "闷响", "回音", "嗓音", "嗓门",
    ),
    "触觉": (
        "发冷", "发烫", "冰凉", "温度", "滚烫", "暖和", "刺痛", "发麻", "僵硬",
        "粗糙", "湿", "黏", "硌", "压着", "发颤", "手心",
    ),
    # 注意：不含裸「味」——「意味着 / 趣味」会误命中
    "嗅觉": ("气味", "味道", "香味", "臭味", "腥", "呛", "臊", "霉味", "油烟"),
    "味觉": ("苦", "甜", "酸", "咸", "涩", "辣", "舌根", "嘴里", "咽下", "嚼"),
    "身体": (
        "喉咙", "胃", "膝盖", "肩膀", "后背", "指尖", "骨头", "汗", "脖子",
        "头皮", "胸口", "小腹", "牙", "腿", "手指",
    ),
    "视觉": (
        "看见", "看到", "亮", "暗", "光", "影子", "颜色", "红", "白", "黑",
        "蓝", "黄", "绿", "眼前", "视线",
    ),
}

# 语病诊断手册 2.3「动作A → 连接 → 动作B → 目的」
ACTION_CHAIN_CONNECTORS = ("然后", "接着", "于是", "随后", "随即", "跟着又")

# 语病诊断手册 2.5「因为A所以B然后C」
CAUSAL_CONNECTORS = ("因为", "由于", "所以", "因此", "因而", "故而", "以致")

# 语病诊断手册 2.9「正在 / 正准备 / 刚要 大部分时候多余」
TIME_ADVERBS = ("正在", "正准备", "正要", "刚要", "刚想", "正打算", "准备要")

# 语病诊断手册 2.4「抽象的『情感词』给角色贴标签」
EMOTION_NOUNS = ("恐惧", "感动", "愤怒", "悲伤", "惊讶", "紧张", "兴奋", "害怕",
                 "难过", "开心", "痛苦", "绝望", "喜悦", "不安", "愧疚", "委屈",
                 "欣慰", "惆怅", "失落", "温暖", "震撼", "厌恶")
EMOTION_LABEL_PATTERN = re.compile(
    r"(?:感到|感觉到|充满|涌起|泛起|升起|深深地|非常|十分|无比|格外|不由得)"
    r"了?(?:一阵|一丝|一种|一股|有些|有点)?"
    r"(?:" + "|".join(EMOTION_NOUNS) + r")"
)

# 语病诊断手册 2.8 段尾「盖章确认」（句式取自该节 ❌ 示例及其近亲）
SUMMARY_ENDING_PATTERNS = (
    re.compile(r"这就是[^。！？]{0,12}的(?:残酷|本质|真相|意义|代价|样子)"),
    re.compile(r"(?:终于|终究|到底)还是(?:来了|到了|来了。)"),
    re.compile(r"不管(?:怎么|怎样|如何)[，,]"),
    re.compile(r"他(?:知道|明白|清楚)[，,][^。！？]{0,20}(?:终于|已经|再也)"),
    re.compile(r"(?:从此|自此)(?:以后|之后)?"),
    re.compile(r"(?:也许|或许)[，,]?这就是"),
    re.compile(r"这一切[，,]?(?:都)?(?:说明|意味着|指向)"),
)

# 语病诊断手册 2.6 清单式罗列：数词 + 量词 + 名词
LISTING_PATTERN = re.compile(r"[一二两三四五六七八九十]\s*[张把盆幅棵扇道座间件个只]")

# 原则 2「人不做多余的数学」：叙述里的精确数值 + 计量单位
PRECISE_UNIT_PATTERN = re.compile(
    r"[〇零一二两三四五六七八九十百千万\d]+\s*"
    r"(?:步|米|厘米|毫米|公里|分钟|秒|小时|天|斤|克|公斤|度|剑|刀|下|层|级|%)"
)

# 语病诊断手册 2.7 停顿段：无对话、无量化、只写状态/感知
PAUSE_HINTS = ("静", "停", "等", "看", "听", "坐", "站", "发呆", "没有说话", "没说话", "沉默")

_DIALOGUE_MARKS = ("「", "」", "“", "”")
_SENT_BOUNDARY = re.compile(r"[^。！？…]*[。！？…]+|[^。！？…]+")
_CLOSERS = "」』”\"）)】"
_REDUPLICATION = re.compile(r"([\u4e00-\u9fff])\1")
_SHORT_SENTENCE_CHARS = 8
_VERY_SHORT_SENTENCE_CHARS = 5
_UNIFORM_RELATIVE_TOLERANCE = 0.25


@dataclass
class Metrics:
    """一章正文的量化画像。"""

    cjk: int = 0
    sentence_count: int = 0
    narrative_sentence_count: int = 0
    sentence_lengths: list[int] = field(default_factory=list)
    sentence_cv: float = 0.0
    longest_uniform_run: int = 0
    short_sentence_ratio: float = 0.0
    very_short_count: int = 0
    paragraph_count: int = 0
    paragraph_lengths: list[int] = field(default_factory=list)
    paragraph_cv: float = 0.0
    short_paragraph_ratio: float = 0.0
    longest_uniform_paragraph_run: int = 0
    dialogue_line_ratio: float = 0.0
    longest_uniform_dialogue_run: int = 0
    ba_sentence_count: int = 0
    ba_density: float = 0.0
    colloquial_density: float = 0.0
    reduplication_count: int = 0
    sensory_channels: list[str] = field(default_factory=list)
    missing_sensory: list[str] = field(default_factory=list)
    pause_paragraph_count: int = 0
    listing_paragraph_count: int = 0
    action_chain_count: int = 0
    causal_chain_count: int = 0
    time_adverb_count: int = 0
    emotion_label_count: int = 0
    summary_ending_count: int = 0
    precise_unit_count: int = 0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["sentence_lengths"] = list(self.sentence_lengths)
        d["paragraph_lengths"] = list(self.paragraph_lengths)
        return d


@dataclass
class Finding:
    level: str          # warn / info
    direction: str      # 缺少 / 出现
    rule: str
    metric: str
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "direction": self.direction,
            "rule": self.rule,
            "metric": self.metric,
            "message": self.message,
        }


# --- 基础工具 ---------------------------------------------------------------

def visible_len(text: str) -> int:
    """句子/段落的可见长度：忽略空白（掩码后的面板会变成空白）。"""
    return len(re.sub(r"\s", "", text))


def split_sentences(text: str) -> list[str]:
    """切句。收尾的引号/括号并入上一句，避免「你好。」被切成两段。"""
    rough = [s.strip() for s in _SENT_BOUNDARY.findall(text)]
    rough = [s for s in rough if s]
    out: list[str] = []
    for s in rough:
        if out and s[0] in _CLOSERS:
            out[-1] += s
        else:
            out.append(s)
    return out


def _cv(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean <= 0:
        return 0.0
    return statistics.pstdev(values) / mean


def _longest_uniform_run(values: list[int]) -> int:
    """最长「长度相近」串：整串的相对跨度（极差 / 均值）不超过容差。

    注意用的是**整串跨度**而不是两两相邻差：28 → 21 → 16 每一步差 25%，
    但整串是单调递降、跨度 43%，读起来是"在收"，不是"平"；而 29 → 25 → 28
    跨度只有 15%，才是真正读不出起伏的均匀叙述。

    朴素实现是 O(n²)，整本 30 万字（约 1.2 万句）要跑 30 秒。这里加两条剪枝，
    语义与朴素实现完全一致（`test_draft_metrics.py` 里有对拍断言）：

    1. **必要条件剪枝**（内层）：有效性要求 `max - min <= tol * mean`，而
       `mean <= max`，故必有 `min >= (1 - tol) * max`。固定起点 `i` 时 `min`
       随 `j` 只减、`max` 只增 —— 一旦该必要条件被破坏，它**永远不会**再成立，
       所以可以 `break` 而不是 `continue`。
    2. **剩余长度剪枝**（外层）：从 `i` 起最长的可能串只有 `n - i` 句，
       若 `n - i <= best` 则后面都不可能刷新纪录，直接结束。
    """
    n = len(values)
    if n == 0:
        return 0
    best = 1
    ratio_floor = 1.0 - _UNIFORM_RELATIVE_TOLERANCE
    for i in range(n):
        if n - i <= best:
            break
        lo = hi = values[i]
        total = values[i]
        for j in range(i + 1, n):
            v = values[j]
            lo = min(lo, v)
            hi = max(hi, v)
            total += v
            if lo < ratio_floor * hi:
                break
            mean = total / (j - i + 1)
            if mean <= 0 or (hi - lo) > _UNIFORM_RELATIVE_TOLERANCE * mean:
                continue
            best = max(best, j - i + 1)
    return best


def _has_dialogue(line: str) -> bool:
    return any(m in line for m in _DIALOGUE_MARKS)


def _narrative(text: str) -> str:
    """去掉「」内的对白，只留叙述部分（对白里的口语词不算违规）。"""
    return re.sub(r"「[^」]*」", "", text)


def _count_occurrences(text: str, words) -> int:
    return sum(text.count(w) for w in words)


def _count_matches(text: str, patterns) -> int:
    return sum(len(p.findall(text)) for p in patterns)


# --- 主分析 -----------------------------------------------------------------

def analyze(text: str) -> Metrics:
    """对一章正文计算量化画像。输入为原始 Markdown 正文。"""
    masked = mask_text(text)
    m = Metrics(cjk=count_cjk(masked))

    paragraphs = [ln.strip() for ln in masked.splitlines() if ln.strip()]
    m.paragraph_count = len(paragraphs)
    m.paragraph_lengths = [visible_len(p) for p in paragraphs]
    m.paragraph_cv = _cv(m.paragraph_lengths)
    if m.paragraph_lengths:
        short_paras = sum(1 for n in m.paragraph_lengths if n <= 15)
        m.short_paragraph_ratio = short_paras / len(m.paragraph_lengths)
    m.longest_uniform_paragraph_run = _longest_uniform_run(m.paragraph_lengths)

    # --- 句子级 ---
    # 叙述节奏只看**叙述句**：对白天然短、天然长度相近，混进来会污染节奏判定
    # （对白节奏由 longest_uniform_dialogue_run 单独度量）。
    sentences: list[str] = []
    for p in paragraphs:
        sentences.extend(split_sentences(p))
    m.sentence_count = len(sentences)
    m.sentence_lengths = [visible_len(s) for s in sentences]

    narr_lengths = [visible_len(s) for s in sentences if not _has_dialogue(s)]
    dialogue_lengths = [visible_len(s) for s in sentences if _has_dialogue(s)]
    m.narrative_sentence_count = len(narr_lengths)
    m.sentence_cv = _cv(narr_lengths)
    if narr_lengths:
        m.short_sentence_ratio = sum(1 for n in narr_lengths if n <= _SHORT_SENTENCE_CHARS) / len(narr_lengths)
        m.very_short_count = sum(1 for n in narr_lengths if n <= _VERY_SHORT_SENTENCE_CHARS)
    m.longest_uniform_run = _longest_uniform_run(narr_lengths)

    # --- 对话 ---
    if paragraphs:
        m.dialogue_line_ratio = sum(1 for p in paragraphs if _has_dialogue(p)) / len(paragraphs)
    m.longest_uniform_dialogue_run = _longest_uniform_run(dialogue_lengths)

    narrative = _narrative(masked)

    # --- 4.4 把字句 ---
    # 排除两类非介词用法：量词（那/这/一/两…+把）与器物名词（把手/把柄/把戏/把关/把守/把门）
    ba_hits = re.findall(r"(?<![一二两三四五六七八九十数几那这哪好几])把(?![手柄戏关守门把])", narrative)
    m.ba_sentence_count = len(ba_hits)
    m.ba_density = m.ba_sentence_count / max(1, m.cjk) * 1000

    # --- 4.6 / 原则 1 口语标记密度 ---
    m.colloquial_density = _count_occurrences(narrative, COLLOQUIAL_MARKERS) / max(1, m.cjk) * 1000

    # --- 4.5 / 2.11 重复强调 ---
    m.reduplication_count = len(_REDUPLICATION.findall(narrative))

    # --- 场景三维度：感官通道覆盖 ---
    present = [ch for ch, words in SENSORY_LEXICON.items() if _count_occurrences(masked, words) > 0]
    m.sensory_channels = present
    m.missing_sensory = [ch for ch in SENSORY_LEXICON if ch not in present]

    # --- 2.7 停顿段 ---
    m.pause_paragraph_count = sum(
        1 for p in paragraphs
        if not _has_dialogue(p)
        and visible_len(p) <= 25
        and any(h in p for h in PAUSE_HINTS)
        and len(LISTING_PATTERN.findall(p)) == 0
    )

    # --- 2.6 清单式罗列 ---
    m.listing_paragraph_count = sum(
        1 for p in paragraphs if len(LISTING_PATTERN.findall(p)) > THRESHOLDS["listing_items_max"]
    )

    # --- 减法项（check_draft 未覆盖的几条） ---
    m.action_chain_count = _count_occurrences(narrative, ACTION_CHAIN_CONNECTORS)
    m.causal_chain_count = _count_occurrences(narrative, CAUSAL_CONNECTORS)
    m.time_adverb_count = _count_occurrences(narrative, TIME_ADVERBS)
    m.emotion_label_count = len(EMOTION_LABEL_PATTERN.findall(narrative))
    m.summary_ending_count = 0
    for p in paragraphs:
        tail = split_sentences(p)
        if tail and _count_matches(tail[-1], SUMMARY_ENDING_PATTERNS):
            m.summary_ending_count += 1
    m.precise_unit_count = len(PRECISE_UNIT_PATTERN.findall(narrative))

    return m


def findings(m: Metrics) -> list[Finding]:
    """把画像转成可读的改进提示。加法项（缺少）排在前，减法项（出现）在后。"""
    out: list[Finding] = []

    if m.sentence_count < 5:
        out.append(Finding("info", "缺少", "—", "sample", "正文句子过少，以下判断仅供参考"))

    # ===== 加法侧：缺了什么 =====
    if m.longest_uniform_run > THRESHOLDS["uniform_run_max"]:
        out.append(Finding(
            "warn", "缺少", "句式节奏档案 4.1「相邻三句的长度不要相近」", "longest_uniform_run",
            f"连续 {m.longest_uniform_run} 句长度相近"
            f"（上限 {THRESHOLDS['uniform_run_max']} 句）——长-短-长或短-短-长，总之不要均匀",
        ))
    if m.very_short_count < THRESHOLDS["very_short_sentence_min"]:
        out.append(Finding(
            "warn", "缺少", "句式节奏档案 4.1「还差一点。（极短，强调）」", "very_short_count",
            f"全文没有一句 5 字以内的极短句（叙述句共 {m.narrative_sentence_count} 句）"
            "——短句是用来砸重量的，没有就没有落点",
        ))
    if m.longest_uniform_paragraph_run > THRESHOLDS["uniform_paragraph_run_max"]:
        out.append(Finding(
            "warn", "缺少", "writing-execution-map「不连续堆同长度短段」", "longest_uniform_paragraph_run",
            f"连续 {m.longest_uniform_paragraph_run} 段长度相近"
            f"（上限 {THRESHOLDS['uniform_paragraph_run_max']}）——段落堆成同一个模子，读者会失去落点",
        ))
    if m.longest_uniform_dialogue_run > THRESHOLDS["uniform_dialogue_run_max"]:
        out.append(Finding(
            "warn", "缺少", "写作Agent Step 4「通篇一问一答」", "longest_uniform_dialogue_run",
            f"连续 {m.longest_uniform_dialogue_run} 轮对话长度相近"
            f"（上限 {THRESHOLDS['uniform_dialogue_run_max']}）——像问答说明书，"
            "可加答非所问、只说一半、动作打断",
        ))
    nonvisual = [c for c in m.sensory_channels if c != "视觉"]
    if len(nonvisual) < THRESHOLDS["narrative_nonvisual_min"]:
        out.append(Finding(
            "warn", "缺少", "写作Agent 场景三维度·感知", "sensory_channels",
            "除视觉外没有任何感官通道（触觉/听觉/嗅觉/味觉/身体）"
            "——规则要求「视觉之外至少补触觉、听觉、嗅觉或身体细节」",
        ))
    if m.colloquial_density < THRESHOLDS["colloquial_density_min"]:
        out.append(Finding(
            "warn", "缺少", "SKILL 原则 1「人写东西是有废话的」+ 句式节奏档案 4.6", "colloquial_density",
            f"口语标记密度 {m.colloquial_density:.2f}/千字"
            f"（参考 {THRESHOLDS['colloquial_density_min']}/千字）——太干净，缺少口气",
        ))
    if m.reduplication_count < THRESHOLDS["reduplication_min"]:
        out.append(Finding(
            "warn", "缺少", "语病诊断手册 2.11「全文没有一个词是重复的 → 违规」", "reduplication_count",
            "全文 0 处叠词/重复强调（点点头、黑乎乎、沉默。沉默。）——AI 觉得重复是浪费，人拿它做节奏",
        ))
    if m.ba_sentence_count == 0 and m.cjk >= 800:
        out.append(Finding(
            "info", "缺少", "句式节奏档案 4.4「把」字句", "ba_sentence_count",
            "全章 0 处「把」字句——中文口语的标志性结构，日常动作可优先用它",
        ))
    if m.pause_paragraph_count < THRESHOLDS["pause_paragraph_min"] \
            and m.cjk >= THRESHOLDS["pause_check_min_cjk"]:
        out.append(Finding(
            "info", "缺少", "语病诊断手册 2.7「插入一段什么也没发生的文字」", "pause_paragraph_count",
            "没有找到停顿段——每段都在推进剧情，缺呼吸空间",
        ))

    # ===== 减法侧：多了什么（check_draft 未覆盖的部分）=====
    if m.summary_ending_count > THRESHOLDS["summary_ending_tolerance"]:
        out.append(Finding(
            "warn", "出现", "语病诊断手册 2.8 标准答案式结尾", "summary_ending_count",
            f"{m.summary_ending_count} 处段尾「盖章总结」——段尾就是段尾，不需要替读者下结论",
        ))
    if m.action_chain_count > THRESHOLDS["action_chain_tolerance"]:
        out.append(Finding(
            "warn", "出现", "语病诊断手册 2.3 动作描写过度完整", "action_chain_count",
            f"{m.action_chain_count} 处「然后/接着/于是」式完整动作链"
            "——连续日常动作可直接跳到关键结果",
        ))
    if m.causal_chain_count > THRESHOLDS["causal_chain_tolerance"]:
        out.append(Finding(
            "warn", "出现", "语病诊断手册 2.5 因果链过度完整", "causal_chain_count",
            f"{m.causal_chain_count} 处叙述内因果连接词——结果已经说明一切时，删掉原因",
        ))
    if m.emotion_label_count > THRESHOLDS["emotion_label_tolerance"]:
        out.append(Finding(
            "warn", "出现", "语病诊断手册 2.4 情感标签化", "emotion_label_count",
            f"{m.emotion_label_count} 处「感到/充满 + 情感词」——能写身体反应就不要写心理感受",
        ))
    if m.time_adverb_count > THRESHOLDS["time_adverb_tolerance"]:
        out.append(Finding(
            "warn", "出现", "语病诊断手册 2.9 多余时间副词", "time_adverb_count",
            f"{m.time_adverb_count} 处「正在/正准备/刚要」——大部分时候多余，直接写动作",
        ))
    if m.listing_paragraph_count > 0:
        out.append(Finding(
            "warn", "出现", "语病诊断手册 2.6 全方位观察综合征", "listing_paragraph_count",
            f"{m.listing_paragraph_count} 个段落是「数词+量词」清单式罗列"
            "——环境只写角色当前会注意到的东西，挑 2-3 个特征",
        ))
    if m.precise_unit_count > THRESHOLDS["precise_unit_tolerance"]:
        out.append(Finding(
            "info", "出现", "SKILL 原则 2「人不做多余的数学」", "precise_unit_count",
            f"{m.precise_unit_count} 处叙述内精确数值+单位——靠感觉和对比，别做多余的数学",
        ))

    return out


# --- CLI --------------------------------------------------------------------

def _print_report(path: Path, m: Metrics, items: list[Finding], as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "path": str(path),
            "metrics": m.to_dict(),
            "findings": [f.to_dict() for f in items],
        }, ensure_ascii=False, indent=2))
        return

    print(f"\n=== {path.name} ===")
    print(f"  汉字 {m.cjk} | 句 {m.sentence_count} 段 {m.paragraph_count} "
          f"| 对话行占比 {m.dialogue_line_ratio:.0%}")
    print(f"  句长 CV {m.sentence_cv:.2f} | 最长均匀句串 {m.longest_uniform_run} "
          f"| 短句占比 {m.short_sentence_ratio:.0%} | 段落 CV {m.paragraph_cv:.2f}")
    print(f"  感官通道 {('/'.join(m.sensory_channels)) or '无'}")
    print(f"  把字句 {m.ba_sentence_count} | 口语标记 {m.colloquial_density:.2f}/千字 "
          f"| 重复强调 {m.reduplication_count} | 停顿段 {m.pause_paragraph_count}")
    if not items:
        print("  ✓ 未发现改进项")
        return
    for f in items:
        mark = {"warn": "!", "info": "·"}.get(f.level, "?")
        print(f"  {mark} [{f.direction}] {f.metric}: {f.message}")
        print(f"      来源：{f.rule}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent_core.draft_metrics",
        description="正文「人味/节奏」画像：补齐 check_draft 只做减法的盲区",
    )
    parser.add_argument("targets", nargs="+", help="正文文件或目录（目录会递归找 正文/*.md）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true", help="存在 warn 时以退出码 1 结束")
    parser.add_argument("--allow-empty", action="store_true",
                        help="一个正文文件都没找到时不报错（供 CI 在 projects/ 为空时使用）")
    args = parser.parse_args(argv)

    files = collect_files(args.targets)
    if not files:
        if not args.allow_empty:
            print("没有找到可分析的正文文件。", file=sys.stderr)
        return 0

    warn_total = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"读取失败 {path}: {exc}", file=sys.stderr)
            continue
        m = analyze(text)
        items = findings(m)
        warn_total += sum(1 for f in items if f.level == "warn")
        _print_report(path, m, items, args.json)
        if args.json:
            continue

    if not args.json:
        print(f"\n合计：{len(files)} 个文件，{warn_total} 条 warn")
    return 1 if (args.strict and warn_total) else 0


if __name__ == "__main__":
    raise SystemExit(main())

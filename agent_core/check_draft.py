"""正文自检：把 `.harness` 规则里**可机器判定**的条款落成确定性校验。

设计原则：本工具的每一条检查项都必须能追溯到仓库里已有的规则文件，
不自行发明标准。规则源：

- `.harness/rules/maps/draft-output-map.md`                   正文路径与落盘约定
- `.harness/rules/maps/writing-execution-map.md`              单段/单句长度上限
- `.harness/skills/human-linguistics/rules/语病诊断手册.md`    T0 禁句、指纹词、进行病、身份标签、过渡词
- `.harness/skills/human-linguistics/references/参考_AI人性化正则规则.md`  AI 废话短语、标点规范化
- `.harness/cases/feedback/2026-09-24-数字生硬.md`             数字算式独立成行

用法：

    python -m agent_core.check_draft <文件或目录>... [--target 2500] [--json]

目录输入会递归查找 `正文/*.md`。
退出码：0 = 无 error；1 = 存在 error。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --- 规则表（来源见模块 docstring） -----------------------------------------

# 语病诊断手册 2.12：绝对禁用
BANNED_WORDS = ("赋能", "抓手", "底层逻辑")
# 语病诊断手册 2.12：★★★ 高危指纹词
HIGH_RISK_FINGERPRINTS = ("全方位", "凸显", "彰显", "加持", "助力")
# 语病诊断手册 2.12：其余指纹词
FINGERPRINTS = (
    "迭代", "闭环", "复盘", "对齐", "维度", "沉淀",
    "心智", "破圈", "出圈", "触达", "洞见", "洞察",
)
# 参考_AI人性化正则规则 8.1：默认删除的 AI 废话短语
AI_FILLER_PHRASES = (
    "综上所述", "总而言之", "由此可见", "不难发现", "需要指出的是",
    "值得一提的是", "值得注意的是", "从某种意义上说", "在一定程度上",
    "就目前来看", "概括来说", "归根结底",
)
# 语病诊断手册 2.14：高危判定式短句
JUDGEMENT_PREFIXES = (
    "没错。", "确实如此。", "也就是说", "换句话说",
    "这意味着", "这说明", "他终于明白",
)
# 语病诊断手册 2.1：连续两段以这些词开头即违规
TRANSITION_STARTERS = ("不过", "但是", "然而")

# 语病诊断手册 2.14 硬性限制：正文叙述默认禁用
T0_PATTERN = re.compile(r"不是[^，。！？\n「」]{1,20}[，。]\s*(?:而是)?是[^，。！？\n「」]{1,20}")
# 语病诊断手册 2.13：进行病
VERB_NOUN_PATTERN = re.compile(r"(进行|实施|做出|采取)(?:了|着)?[\u4e00-\u9fff]{1,4}")
# 语病诊断手册 2.10：身份重复标签
IDENTITY_TAG_PATTERN = re.compile(r"(作为|身为)[^，。！？\n]{1,15}的")
# 反馈案例：算式独立成行
FORMULA_LINE_PATTERN = re.compile(r"^\s*[\d.]+\s*[+\-*/×÷]\s*[\d.]+(?:\s*[+\-*/×÷]\s*[\d.]+)*\s*=")
# 参考_AI人性化正则规则 5.x：标点规范化
PUNCT_PATTERNS = (
    ('"', "ASCII 直双引号，应为「」", None),
    (r"\.{3,}", "半角省略号，应为……", None),
    (r"(?<!-)--+(?!-)", "半角破折号，应为——", None),
)

SENTENCE_SPLIT = re.compile(r"[。！？…]+")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")

# 长度上限（writing-execution-map「段落与句子」）
MAX_PARAGRAPH_CHARS = 60
MAX_SENTENCE_CHARS = 45

LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}


@dataclass
class Issue:
    level: str
    rule: str
    line: int
    message: str
    excerpt: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "rule": self.rule,
            "line": self.line,
            "message": self.message,
            "excerpt": self.excerpt,
        }


def count_cjk(text: str) -> int:
    """按汉字个数计字，与项目内「3033 汉字」的口径一致。"""
    return len(CJK_PATTERN.findall(text))


def mask_text(text: str) -> str:
    """屏蔽不参与校验的区域：代码块、系统面板、Markdown 标题/表格/分割线。

    用等长空白替换，保持行号与列位置不变，便于后续定位。
    """
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out_lines.append(" " * len(line))
            continue
        if in_fence:
            out_lines.append(" " * len(line))
            continue
        if stripped.startswith(("#", "|")) or re.fullmatch(r"[-*_=]{3,}", stripped):
            out_lines.append(" " * len(line))
            continue
        # 行内系统面板（参考_AI人性化正则规则 4.1）
        line = re.sub(r"【[^】]*】", lambda m: " " * len(m.group(0)), line)
        out_lines.append(line)
    return "\n".join(out_lines)


def _inside_quote(line: str, pos: int) -> bool:
    """判断 pos 处是否落在「」内（即角色对白）。"""
    return line.count("「", 0, pos) > line.count("」", 0, pos)


def check_text(text: str, path: Path | None = None, target_words: int | None = None) -> list[Issue]:
    issues: list[Issue] = []
    masked = mask_text(text)
    lines = masked.splitlines()
    raw_lines = text.splitlines()

    def excerpt(i: int) -> str:
        return raw_lines[i].strip()[:60] if 0 <= i < len(raw_lines) else ""

    # --- 逐行检查 ---
    for idx, line in enumerate(lines):
        if not line.strip():
            continue

        for word in BANNED_WORDS:
            if word in line:
                issues.append(Issue("error", "语病诊断手册 2.12 · 绝对禁用词", idx + 1,
                                    f"出现绝对禁用指纹词「{word}」", excerpt(idx)))

        for word in HIGH_RISK_FINGERPRINTS:
            if word in line:
                issues.append(Issue("warn", "语病诊断手册 2.12 · ★★★ 指纹词", idx + 1,
                                    f"高危指纹词「{word}」", excerpt(idx)))

        for word in FINGERPRINTS:
            if word in line:
                issues.append(Issue("warn", "语病诊断手册 2.12 · 指纹词", idx + 1,
                                    f"指纹词「{word}」", excerpt(idx)))

        for phrase in AI_FILLER_PHRASES:
            if phrase in line:
                issues.append(Issue("warn", "参考_AI人性化正则规则 8.1 · AI 废话短语", idx + 1,
                                    f"废话短语「{phrase}」", excerpt(idx)))

        for prefix in JUDGEMENT_PREFIXES:
            if prefix in line:
                issues.append(Issue("warn", "语病诊断手册 2.14 · 判定式短句", idx + 1,
                                    f"判定式短句「{prefix}」", excerpt(idx)))

        for match in VERB_NOUN_PATTERN.finditer(line):
            issues.append(Issue("warn", "语病诊断手册 2.13 · 进行病", idx + 1,
                                f"「{match.group(1)}」式万能动词，可换具体动词", excerpt(idx)))

        for match in IDENTITY_TAG_PATTERN.finditer(line):
            issues.append(Issue("warn", "语病诊断手册 2.10 · 身份重复标签", idx + 1,
                                f"「{match.group(0)}」", excerpt(idx)))

        for pattern, desc, _ in PUNCT_PATTERNS:
            if re.search(pattern, line):
                issues.append(Issue("warn", "参考_AI人性化正则规则 5 · 标点规范化", idx + 1,
                                    desc, excerpt(idx)))

        if FORMULA_LINE_PATTERN.match(line):
            issues.append(Issue("warn", "反馈案例 2026-09-24 · 算式顶替动作", idx + 1,
                                "算式独立成行", excerpt(idx)))

        for match in T0_PATTERN.finditer(line):
            if _inside_quote(line, match.start()):
                issues.append(Issue("info", "语病诊断手册 2.14 · T0 禁句（对白）", idx + 1,
                                    f"对白内 T0 句式「{match.group(0)}」", excerpt(idx)))
            else:
                issues.append(Issue("error", "语病诊断手册 2.14 · T0 禁句（叙述）", idx + 1,
                                    f"叙述中命中 T0 禁句「{match.group(0)}」", excerpt(idx)))

    # --- 段落级检查 ---
    paragraphs = []  # (起始行号, 文本)
    buf: list[str] = []
    start = 1
    for idx, line in enumerate(lines):
        if line.strip():
            if not buf:
                start = idx + 1
            buf.append(line.strip())
        elif buf:
            paragraphs.append((start, "".join(buf)))
            buf = []
    if buf:
        paragraphs.append((start, "".join(buf)))

    for line_no, para in paragraphs:
        length = len(para)
        if length > MAX_PARAGRAPH_CHARS:
            issues.append(Issue("warn", "writing-execution-map · 段落与句子", line_no,
                                f"单段 {length} 字，超过 {MAX_PARAGRAPH_CHARS} 字上限", para[:60]))
        for sentence in SENTENCE_SPLIT.split(para):
            if len(sentence) > MAX_SENTENCE_CHARS:
                issues.append(Issue("warn", "writing-execution-map · 段落与句子", line_no,
                                    f"单句 {len(sentence)} 字，超过 {MAX_SENTENCE_CHARS} 字上限", sentence[:60]))

    # 语病诊断手册 2.1：连续两段以过渡词开头
    prev_was_transition = False
    for line_no, para in paragraphs:
        current = any(para.startswith(word) for word in TRANSITION_STARTERS)
        if current and prev_was_transition:
            issues.append(Issue("warn", "语病诊断手册 2.1 · 过渡词过度", line_no,
                                "连续两段以过渡词开头", para[:40]))
        prev_was_transition = current

    # --- 字数 ---
    words = count_cjk(text)
    if target_words:
        delta = words - target_words
        if abs(delta) > target_words * 0.1:
            direction = "偏少" if delta < 0 else "偏多"
            issues.append(Issue("warn", "draft-output-map · 字数门禁", 0,
                                f"{words} 汉字，较目标 {target_words} {direction} {abs(delta)} 字"))

    return issues


def check_path(path: Path) -> list[Issue]:
    """按 draft-output-map 校验正文路径：projects/{项目}/正文/第N章.md"""
    parts = path.as_posix().split("/")
    issues: list[Issue] = []
    if "projects" not in parts or "正文" not in parts:
        issues.append(Issue("error", "draft-output-map · 正文文件定位", 0,
                            f"路径不含 projects/{{项目}}/正文/ 结构：{path}"))
        return issues
    pidx = parts.index("projects")
    if pidx + 2 >= len(parts) or parts[pidx + 2] != "正文":
        issues.append(Issue("error", "draft-output-map · 正文文件定位", 0,
                            f"正文未落在 projects/{{项目}}/正文/ 下：{path}"))
    return issues


def collect_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in targets:
        path = Path(raw)
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            found = sorted(path.rglob("正文/*.md"))
            if not found:
                found = sorted(path.rglob("*.md"))
            files.extend(found)
            continue
        print(f"跳过：{raw}（不存在）", file=sys.stderr)
    return files


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="按 .harness 既有规则做正文自检")
    parser.add_argument("targets", nargs="+", help="正文文件或项目目录")
    parser.add_argument("--target", type=int, default=None, help="目标字数，用于偏差提示")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--strict", action="store_true", help="warn 也计入失败退出码")
    args = parser.parse_args(argv)

    files = collect_files(args.targets)
    if not files:
        print("未找到可校验的正文文件。", file=sys.stderr)
        return 1

    report = []
    error_total = warn_total = 0

    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        issues = check_path(path) + check_text(text, path, args.target)
        issues.sort(key=lambda item: (item.line, LEVEL_ORDER[item.level]))
        errors = sum(1 for item in issues if item.level == "error")
        warns = sum(1 for item in issues if item.level == "warn")
        error_total += errors
        warn_total += warns
        report.append({
            "file": str(path),
            "words": count_cjk(text),
            "error": errors,
            "warn": warns,
            "issues": [item.to_dict() for item in issues],
        })

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for entry in report:
            print(f"\n{entry['file']}  ·  {entry['words']} 汉字  ·  "
                  f"{entry['error']} error / {entry['warn']} warn")
            for item in entry["issues"]:
                mark = {"error": "x", "warn": "!", "info": "i"}[item["level"]]
                where = f"L{item['line']}" if item["line"] else "--"
                print(f"  [{mark}] {where:>5}  {item['message']}   <- {item['rule']}")

        print(f"\n合计：{len(report)} 个文件，{error_total} error / {warn_total} warn")

    if error_total:
        return 1
    if args.strict and warn_total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

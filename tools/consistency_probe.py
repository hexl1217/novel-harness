"""规则层 ↔ 机器层 ↔ 执行层 一致性探针（只读，不改任何文件）。

用途：在没有 registry 的前提下，先数清楚「三层对不齐」到底有多少处。
答案直接决定要不要建整套 YAML 清单机制。

四类检测：
  P1 机器层引用的规则源文件/小节，在规则层是否真实存在
  P2 机器层判定的级别，与规则层自述是否冲突（如手册说「机器报不出来」却被机器实现）
  P3 执行层文档登记的「机器已覆盖」清单，与机器层实际实现是否一致
  P4 同一规则在机器层/文档层的命名是否一致

运行：python tools/consistency_probe.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK_DRAFT = ROOT / "agent_core" / "check_draft.py"
DRAFT_METRICS = ROOT / "agent_core" / "draft_metrics.py"
HANDBOOK = ROOT / ".harness" / "skills" / "human-linguistics" / "rules" / "语病诊断手册.md"
RHYTHM = ROOT / ".harness" / "skills" / "human-linguistics" / "rules" / "句式节奏档案.md"
CH_REQUIRED = ROOT / ".harness" / "rules" / "maps" / "chapter-required-reading.md"
REVIEW_CHECKLIST = ROOT / ".harness" / "rules" / "maps" / "review-execution-checklist.md"

findings: list[tuple[str, str, str]] = []


def add(kind: str, severity: str, detail: str) -> None:
    findings.append((kind, severity, detail))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def machine_rule_names() -> dict[str, list[str]]:
    """抠出机器层两个脚本里所有「规则来源」字符串。"""
    out: dict[str, list[str]] = {}
    for path in (CHECK_DRAFT, DRAFT_METRICS):
        text = read(path)
        names = set()
        # 形如 "语病诊断手册 2.13 · 进行病" / "句式节奏档案 4.1「…」"
        for m in re.finditer(r'"([^"]*(?:手册|档案|map|Agent|SKILL|原则|反馈案例|参考_AI)[^"]*)"', text):
            names.add(m.group(1))
        out[path.name] = sorted(names)
    return out


def sections(path: Path) -> set[str]:
    """抠出规则文件里的小节号，如 2.3 / 4.1。"""
    return set(re.findall(r"^#{2,4}\s+(\d+\.\d+)", read(path), flags=re.M))


def main() -> int:
    handbook = read(HANDBOOK)
    checklist = read(REVIEW_CHECKLIST)
    machine = machine_rule_names()

    print("=" * 78)
    print("规则层 ↔ 机器层 ↔ 执行层 一致性探针")
    print("=" * 78)

    # ---------- P1：机器层引用的规则文件是否存在 ----------
    print("\n【P1】机器层引用的规则源文件是否真实存在")
    sources = {
        "语病诊断手册": HANDBOOK,
        "句式节奏档案": RHYTHM,
        "writing-execution-map": ROOT / ".harness/rules/maps/writing-execution-map.md",
        "draft-output-map": ROOT / ".harness/rules/maps/draft-output-map.md",
        "写作Agent": ROOT / ".harness/agents/写作Agent.md",
        "参考_AI人性化正则规则": ROOT / ".harness/skills/human-linguistics/references/参考_AI人性化正则规则.md",
        "SKILL": ROOT / ".harness/skills/human-linguistics/SKILL.md",
        "反馈案例": ROOT / ".harness/cases/feedback/2026-09-24-数字生硬.md",
    }
    referenced = set()
    for names in machine.values():
        for n in names:
            for key in sources:
                if key in n:
                    referenced.add(key)
    for key in sorted(referenced):
        ok = sources[key].exists()
        print(f"  {'OK ' if ok else 'MISS'}  {key:<28} -> {sources[key].relative_to(ROOT)}")
        if not ok:
            add("P1", "高", f"机器层引用 {key}，但文件不存在")

    # ---------- P2：手册自述「机器报不出来」却被机器实现 ----------
    print("\n【P2】规则层自述「机器管不了」vs 机器层实际接管")
    # 手册第 20 行附近：先跑 check_draft；只对「它报不出来」的条目人工判断——2.2 …2.11
    m = re.search(r"让它把上面几条报出来；然后只对\*\*它报不出来\*\*的条目逐条人工判断——([^\n]*)", handbook)
    manual_claimed: set[str] = set()
    if m:
        manual_claimed = set(re.findall(r"(\d+\.\d+)", m.group(1)))
        print(f"  手册自述「机器报不出来、需人工判断」的小节：{sorted(manual_claimed)}")

    machine_covers = set()
    for names in machine.values():
        for n in names:
            for s in re.findall(r"语病诊断手册\s*(\d+\.\d+)", n):
                machine_covers.add(s)
    print(f"  机器层实际实现的语病手册小节：{sorted(machine_covers)}")

    overlap = sorted(manual_claimed & machine_covers)
    for s in overlap:
        print(f"  CONFLICT  手册说 {s} 机器报不出来，draft_metrics 却实现了 {s}")
        add("P2", "高", f"语病诊断手册 {s}：手册自称需人工判断，机器层已接管（两边未对齐）")
    if not overlap:
        print("  无冲突")

    # ---------- P3：执行层登记 vs 机器层实现 ----------
    print("\n【P3】执行层文档登记的「机器已覆盖」范围 vs 机器层实际")
    ch = read(CH_REQUIRED)
    claimed_sections: set[str] = set()
    # 表零A / 表零B 表格里的「语病诊断手册 2.10–2.14」「2.3–2.9·2.11」等
    for m in re.finditer(r"语病诊断手册[`\s]*([\d.]+)\s*[–\-—]\s*([\d.]+)", ch):
        lo_major, lo_minor = m.group(1).split(".")
        hi_major, hi_minor = m.group(2).split(".")
        if lo_major == hi_major:
            for i in range(int(lo_minor), int(hi_minor) + 1):
                claimed_sections.add(f"{lo_major}.{i}")
    for m in re.finditer(r"语病诊断手册[`\s]*([\d.]+)(?:[·、]([\d.]+))*", ch):
        claimed_sections.add(m.group(1))
    # 单独列的 2.3 / 2.11 等
    for m in re.finditer(r"(?:^|[·、\s(])(\d+\.\d+)", ch):
        pass

    # 文档表零A/B 各自明确列出的小节（在审稿清单中）。
    # 注意：表零A 用「名称」（进行病/身份重复标签），表零B 用「小节号」（2.3/4.1）。
    # 两边格式不统一，本探针按名称→小节号映射后再比。
    SEC_NAME_TO_ID = {
        "T0 禁句": "2.14", "绝对禁用词": "2.12", "指纹词": "2.12",
        "进行病": "2.13", "身份重复标签": "2.10", "判定式短句": "2.14",
        "过渡词": "2.1", "动作链": "2.3", "情感标签": "2.4", "因果链": "2.5",
        "清单式罗列": "2.6", "段尾盖章": "2.8", "多余时间副词": "2.9",
        "重复强调缺失": "2.11",
    }

    def listed_a() -> set[str]:
        m = re.search(r"表零A 已覆盖[^\n]*?：([^\n]*)", checklist)
        if not m:
            return set()
        found = set()
        for name, sid in SEC_NAME_TO_ID.items():
            if name in m.group(1):
                found.add(sid)
        return found

    def listed_b() -> set[str]:
        m = re.search(r"表零B 已覆盖[^\n]*?：([^\n]*)", checklist)
        return set(re.findall(r"(\d+\.\d+)", m.group(1))) if m else set()

    doc_a = listed_a()
    doc_b = listed_b()

    def impl_sections(filename: str) -> set[str]:
        """抠出某脚本里引用的小节号，覆盖「语病诊断手册 2.x」与「句式节奏档案 4.x」。"""
        out = set()
        for n in machine.get(filename, []):
            out |= set(re.findall(r"语病诊断手册\s*(\d+\.\d+)", n))
            out |= set(re.findall(r"句式节奏档案\s*(\d+\.\d+)", n))
        return out

    cd_sections = impl_sections("check_draft.py")
    dm_sections = impl_sections("draft_metrics.py")

    print(f"  表零A 登记：{sorted(doc_a)}")
    print(f"  check_draft 实现：{sorted(cd_sections)}")
    print(f"  表零B 登记：{sorted(doc_b)}")
    print(f"  draft_metrics 实现：{sorted(dm_sections)}")

    for label, doc, impl in (("A", doc_a, cd_sections), ("B", doc_b, dm_sections)):
        for s in sorted(impl - doc):
            print(f"  GAP  机器层({label})实现 {s}，但表零{label} 覆盖清单未登记")
            add("P3", "中", f"语病诊断手册 {s}：机器已实现，表零{label} 覆盖清单漏登记")
        for s in sorted(doc - impl):
            print(f"  GAP  表零{label} 登记 {s}，但机器层未实现（会被误当已机器化）")
            add("P3", "高", f"语病诊断手册 {s}：表零{label} 登记为机器覆盖，机器层无实现")

    # ---------- P4：命名一致性 ----------
    print("\n【P4】同一规则在机器层/文档层的命名一致")
    # 抽取 check_draft 里 issue 的 rule 名，与文档用语比
    cd_text = read(CHECK_DRAFT)
    issue_names = set(re.findall(r'Issue\([^,]+,\s*"([^"]+)"', cd_text))
    print(f"  check_draft 实际输出的 rule 名（{len(issue_names)} 个）：")
    for n in sorted(issue_names):
        print(f"      {n}")

    # 文档侧对「数字分层」的统一用语
    doc_term = "数字出场分层"
    named = sorted(n for n in issue_names if "数字出场分层" in n)
    others = sorted(n for n in issue_names if "数字出场分层" not in n and "算式" in n)
    if others:
        for c in others:
            print(f"  NAMING  机器层仍用旧称：{c}")
            add("P4", "低", f"「数字分层」命名不一致：机器层称「{c}」，文档层称「{doc_term}」")
    else:
        print(f"  OK  「数字分层」命名已统一为「{doc_term}」（机器层 {len(named)} 条）")

    # ---------- 汇总 ----------
    print("\n" + "=" * 78)
    print(f"合计：{len(findings)} 处不一致")
    by_sev: dict[str, int] = {}
    for _, sev, _ in findings:
        by_sev[sev] = by_sev.get(sev, 0) + 1
    for sev in ("高", "中", "低"):
        if sev in by_sev:
            print(f"  {sev}：{by_sev[sev]}")
    if not findings:
        print("  三层一致性：全部对齐 ✓")
    print("=" * 78)

    # CI 用：有 findings 时返回 1。--strict 之外（默认）也返回 1，
    # 因为本探针只做一致性对账，任何不一致都应被看见。
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

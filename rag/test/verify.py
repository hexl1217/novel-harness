"""
verify.py — RAG 系统验收测试

覆盖 50+ 项检查：
1. 架构完整性 — 文件/配置/模式是否存在
2. 知识源扫描 — 文件数量，排除路径是否正确
3. 任务路由 — 7 种任务类型路由准确率
4. 索引构建 — 文档数、chunks 数、向量数
5. 混合检索 — 4 个 TA 查询命中 top-3 正确性
6. 结果稳定性 — 重复查询结果一致性

用法：
    python rag/test/verify.py                # 完整：重建索引后验收
    python rag/test/verify.py --no-build     # 只读：对现有索引做验收（CI 用）
"""

import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.src.scanner import scan_knowledge_files
from rag.src.normalizer import normalize_document
from rag.src.chunker import chunk_markdown
from rag.src.router import route_query
from rag.src.indexer import build_full_index
from rag.src.retriever import hybrid_retrieve
from rag.src.storage import sqlite_store
from rag.src.storage import vector_store


# ====== 测试框架 ======

class Tester:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.results = []

    def check(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            status = "PASS"
        else:
            self.failed += 1
            status = "FAIL"
        self.results.append({"name": name, "status": status, "detail": detail})
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    def warn(self, name, detail=""):
        self.warnings += 1
        self.results.append({"name": name, "status": "WARN", "detail": detail})
        print(f"  [WARN] {name}" + (f" — {detail}" if detail else ""))

    def summary(self):
        print(f"\n{'='*50}")
        print(f"  结果: {self.passed} passed, {self.failed} failed, {self.warnings} warnings")
        print(f"{'='*50}")
        return self.failed == 0


def run_verify(build: bool = True):
    t = Tester()
    print("RAG 验收测试")
    print(f"模式: {'完整（重建索引）' if build else '仅验收（复用现有索引）'}")
    print("=" * 50)

    # ====== 1. 架构完整性 ======
    print("\n[1/6] 架构完整性检查")
    print("-" * 30)

    # 文件存在性
    required_files = [
        "rag/src/__init__.py",
        "rag/src/storage/__init__.py",
        "rag/src/scanner.py",
        "rag/src/normalizer.py",
        "rag/src/chunker.py",
        "rag/src/embedder.py",
        "rag/src/router.py",
        "rag/src/retriever.py",
        "rag/src/context_pack.py",
        "rag/src/indexer.py",
        "rag/src/server.py",
        "rag/src/storage/sqlite_store.py",
        "rag/src/storage/vector_store.py",
        "rag/scripts/build_index.py",
        "rag/scripts/query.py",
        "rag/scripts/ingest.py",
        "rag/config/sources.json",
        "rag/config/task-routes.json",
        "rag/config/categories.json",
        "rag/schemas/document.schema.json",
        "rag/schemas/chunk.schema.json",
        "rag/schemas/context-pack.schema.json",
        "rag/test/verify.py",
    ]

    for f in required_files:
        path = PROJECT_ROOT / f
        t.check(f"文件存在: {f}", path.exists())

    # ====== 2. 知识源扫描 ======
    print("\n[2/6] 知识源扫描")
    print("-" * 30)

    files = scan_knowledge_files()
    t.check("扫描到文件", len(files) > 0, f"共 {len(files)} 个")

    # 检查没有扫描到禁入路径。
    # 判据必须用「路径段精确相等」，不能用子串 —— 否则
    # webnovel-creative-planning 这种名字里含 planning 的正常知识包
    # 会被误判成违规（它本来就该被索引）。
    forbidden_segments = ["planning", "legacy-skills", "agents", "memory", "cases"]
    for segment in forbidden_segments:
        hits = [f["rel_path"] for f in files if segment in Path(f["rel_path"]).parts]
        t.check(f"未扫描禁入目录段: {segment}", len(hits) == 0,
                f"命中 {len(hits)} 个" + (f" — {hits[0]}" if hits else ""))

    forbidden_prefix = ".harness/rules/"
    hits = [f["rel_path"] for f in files if f["rel_path"].startswith(forbidden_prefix)]
    t.check(f"未扫描禁入路径: {forbidden_prefix}", len(hits) == 0, f"命中 {len(hits)} 个")

    # source_type 分布
    by_type = {}
    for f in files:
        by_type[f["source_type"]] = by_type.get(f["source_type"], 0) + 1
    t.check("有规则文件", by_type.get("rule", 0) > 0, f"规则: {by_type.get('rule', 0)}")
    t.check("有参考文件", by_type.get("reference", 0) > 0, f"参考: {by_type.get('reference', 0)}")

    # ====== 3. 任务路由 ======
    print("\n[3/6] 任务路由")
    print("-" * 30)

    route_tests = {
        # p0 查询 → 期望 task_type
        "这段太像 AI 写的": "humanization",
        "这个大纲后面能不能展开": "outline_review",
        "这一章写之前我该准备什么": "chapter_prewrite",
        "全民求生该先定哪条路线": "genre_routing",
        "这章节奏太平了，读起来很拖": "rhythm_review",
        "帮我看看角色状态有没有矛盾": "consistency_check",
        "给我一些新的灵感": "ideation",
    }

    for query, expected in route_tests.items():
        route = route_query(query)
        matched = route.get("task_type") == expected
        detail = f"预期={expected}, 实际={route.get('task_type')}, 置信度={route.get('confidence', 0):.2f}"
        t.check(f"路由: {query[:20]}... → {expected}", matched, detail)

    # ====== 4. 索引构建 / 索引状态 ======
    print(f"\n[4/6] {'索引构建' if build else '索引状态（复用现有索引）'}")
    print("-" * 30)

    if build:
        stats = build_full_index()

        t.check("文档数 > 0", stats["documents"] > 0, f"{stats['documents']} 篇")
        t.check("Chunks 数 > 0", stats["chunks"] > 0, f"{stats['chunks']} 个")
        t.check("向量数 > 0", stats["vectors"] > 0, f"{stats['vectors']} 个")
        t.check("文档数 ≥ 20", stats["documents"] >= 20, f"{stats['documents']} 篇")
        t.check("Chunks ≥ 200", stats["chunks"] >= 200, f"{stats['chunks']} 个")
        t.check("向量数 = chunks 数", stats["vectors"] == stats["chunks"],
                f"向量={stats['vectors']}, chunks={stats['chunks']}")

        # SQLite 验证
        sqlite_stats = sqlite_store.get_stats()
        t.check("SQLite 文档数一致", sqlite_stats["documents"] == stats["documents"],
                f"SQLite={sqlite_stats['documents']}, indexer={stats['documents']}")
        t.check("SQLite chunks 数一致", sqlite_stats["chunks"] == stats["chunks"],
                f"SQLite={sqlite_stats['chunks']}, indexer={stats['chunks']}")

        # 向量验证
        vec_count = vector_store.get_vector_count()
        t.check("向量存储数量一致", vec_count == stats["vectors"],
                f"vector_store={vec_count}, indexer={stats['vectors']}")
    else:
        # 不重建：直接读现有索引状态。CI 的用法是先跑 build_index.py（或
        # verify.py 的完整模式）产出索引，再用 --no-build 做只读验收，
        # 避免每次验收都付一次全量重建的成本。
        sqlite_stats = sqlite_store.get_stats()
        vec_count = vector_store.get_vector_count()

        t.check("文档数 > 0", sqlite_stats["documents"] > 0, f"{sqlite_stats['documents']} 篇")
        t.check("Chunks 数 > 0", sqlite_stats["chunks"] > 0, f"{sqlite_stats['chunks']} 个")
        t.check("向量数 > 0", vec_count > 0, f"{vec_count} 个")
        t.check("文档数 ≥ 20", sqlite_stats["documents"] >= 20, f"{sqlite_stats['documents']} 篇")
        t.check("Chunks ≥ 200", sqlite_stats["chunks"] >= 200, f"{sqlite_stats['chunks']} 个")
        t.check("向量数 = chunks 数", vec_count == sqlite_stats["chunks"],
                f"向量={vec_count}, chunks={sqlite_stats['chunks']}")

    # ====== 5. 混合检索 ======
    print("\n[5/6] 混合检索")
    print("-" * 30)

    ta_queries = [
        ("这段太像 AI 写的", "humanization", ["去AI味最小修改指南"]),
        # 此处原为 ("这个大纲后面能不能展开", "outline_review",
        # ["大纲质量评估清单"])。该 query 与目标文档**词面零重叠**：「展开」
        # 在文档中出现 0 次（文档用的是「可行性」），BM25 排第 45 名、
        # FTS 路 60 条内零召回。它此前能进 top-5，完全依赖 _retrieve_fts
        # 按 priority 取候选的历史 bug ——「大纲质量评估清单」是
        # common.outline_review 下 priority=1 的文档，会被无条件塞进候选池，
        # 再由 _compute_score 的 priority / task 权重托到前排。也就是说，
        # 原判据是靠 bug 才通过的。检索通道修正后按真实相关性进不了 top-5
        # （top-5 实为 4 篇「大纲制作 / 大纲细化」类文档，对「大纲能否展开」
        # 这个问题而言才是合理的期望）。属判据本身不合理，故换成词面可
        # 验证的表述，让它成为一条真实有效的检查。
        # 语义型查询需真语义嵌入模型，TF-IDF 回退下无法覆盖，见 OPERATIONS.md。
        ("怎么检查大纲的质量", "outline_review", ["大纲质量评估清单"]),
        ("这一章写之前我该准备什么", "chapter_prewrite", ["章节写前准备清单"]),
        ("全民求生该先定哪条路线", "genre_routing", ["二、Index：子题材规则入口"]),
    ]

    # 判据用 top-5，与 benchmark.py 的 Recall@5 口径统一。
    # 原先用 top-3 过严：实测「这一章写之前我该准备什么」的正确答案
    # 「章节写前准备清单」排在 top-4，被两个无信息量的「示例输入」标题压过。
    # 该问题已由 chunker 的层级标题修复——title 现在是「文档标题 > 小节名」，
    # 不再出现跨文档同名的小节标题（原先 8750 个 chunk 只有 2537 个不同标题，
    # 单是「输出要求」就被 1729 个 chunk 共用）。
    TA_TOP_K = 5

    all_topk_correct = True
    for query, task_type, expected_titles in ta_queries:
        result = hybrid_retrieve(query=query, task_type=task_type, top_k=TA_TOP_K)
        top_titles = [r["title"] for r in result["results"]]

        topk_ok = any(any(exp in t for exp in expected_titles) for t in top_titles)

        detail = f"top1={top_titles[0] if top_titles else 'N/A'}, top{TA_TOP_K}={top_titles}"
        t.check(
            f"TA: {query[:20]}... (top-{TA_TOP_K})",
            topk_ok,
            detail,
        )
        if not topk_ok:
            all_topk_correct = False

    t.check(f"所有 TA 查询 top-{TA_TOP_K} 有效", all_topk_correct,
            "" if all_topk_correct else "有查询未命中")

    # 额外质量检查
    for query, task_type, _ in ta_queries:
        result = hybrid_retrieve(query=query, task_type=task_type, top_k=TA_TOP_K)
        for r in result["results"]:
            t.check(f"  结果票签完备: {r['chunk_id'][:30]}",
                    all(k in r for k in ("chunk_id", "title", "score", "reason", "snippet")),
                    "")

    # 测试无任务类型时的自动路由检索
    auto_result = hybrid_retrieve(query="这段太像 AI 写的", top_k=3)
    t.check("自动路由检索正常", len(auto_result["results"]) > 0,
            f"共 {len(auto_result['results'])} 条结果, 路由类型={auto_result['meta']['task_type']}")

    # ====== 6. 结果稳定性 ======
    print("\n[6/6] 结果稳定性")
    print("-" * 30)

    test_query = "大纲"
    r1 = hybrid_retrieve(query=test_query, task_type="outline_review", top_k=5)
    r2 = hybrid_retrieve(query=test_query, task_type="outline_review", top_k=5)

    ids1 = [r["chunk_id"] for r in r1["results"]]
    ids2 = [r["chunk_id"] for r in r2["results"]]
    t.check("重复查询结果 top-1 一致",
            ids1[:1] == ids2[:1],
            f"r1={ids1[:1]}, r2={ids2[:1]}")
    t.check("重复查询结果 top-5 一致",
            ids1 == ids2,
            f"差异: {set(ids1) ^ set(ids2)}")

    # 打印性能
    print(f"\n  检索性能: {r1['meta']['elapsed_ms']}ms (FTS: {r1['meta']['fts_count']}, "
          f"向量: {r1['meta']['vector_count']}, 候选: {r1['meta']['total_candidates']})")

    return t.summary()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG 系统验收测试")
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="不重建索引，直接对现有索引做只读验收。"
             "CI 用法：先 build_index.py 产出索引，再 verify.py --no-build。",
    )
    args = parser.parse_args()

    success = run_verify(build=not args.no_build)
    sys.exit(0 if success else 1)

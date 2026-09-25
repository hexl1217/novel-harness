# agent_core

`.harness` 是给 LLM 读的规则层（Markdown 提示词）；`agent_core` 是**能被机器执行**的那部分规则。

分界原则：

- 需要判断语义、人设、节奏的 → 留在 Markdown，交给 LLM。
- 字面稳定、误伤可控、有明确阈值的 → 放进这里，用代码判，不再靠 LLM 自我申报。

## 模块

| 文件 | 状态 | 说明 |
|:-----|:-----|:-----|
| `check_draft.py` | 可用 | 正文机器预检·**减法**：把规则里「不该出现什么」的条款落成确定性校验 |
| `draft_metrics.py` | 可用 | 正文机器预检·**加法**：把规则里「应该出现什么」的门禁落成量化画像 |
| `state.py` | 可用 | 运行时状态落盘：挂起恢复栈、开书阶段 S0–S5、已锁定题材/平台/知识包 |
| `state_machine.py` | 原型 | 单章流水线状态机（准备–写作–审稿–归档） |
| `engine.py` | 原型 | 引擎外壳，负责串联状态机与落盘 |
| `project.py` | 原型 | 项目存储，路径对齐 `projects/{项目}/正文/第N章.md` |
| `test/` | — | 单元测试，`python -m pytest agent_core/test/` |

## 两个工具为什么必须成对使用

| | `check_draft` | `draft_metrics` |
|:--|:--|:--|
| 方向 | **减法** —— 不该出现什么 | **加法** —— 应该出现什么 |
| 典型问题 | 判定式短句、指纹词、段落超长 | 节奏均匀、只有视觉一种感官、通篇没有一句极短句 |
| 级别 | 含 `error`，是**硬门禁** | 只有 `warn` / `info`，是**画像与提示** |
| 判据形态 | 词表匹配 | 统计量（长度分布、密度、覆盖） |

**只跑 `check_draft` 会漏掉整整一类问题**：`check_draft` 全绿、每个字都合规，
但读起来仍然一眼是 AI —— 因为所有 AI 味都去掉了，也什么都没加进去。
规则文件里那批带「门禁」字样的加法条款（长短句交替、极短句强调、重复强调缺失、
感官通道、心理代偿）此前**一条都没有被机器化**。

## draft_metrics 用法

```bash
# 单章
python -m agent_core.draft_metrics projects/迷雾民宿/正文/第1章.md

# 整个项目（递归找 正文/*.md）
python -m agent_core.draft_metrics projects/迷雾民宿

# JSON 输出 / 把 warn 也当失败（用于 CI 或 pre-commit）
python -m agent_core.draft_metrics 第1章.md --json --strict
```

Makefile 入口：

```bash
make draft-metrics DRAFT=projects/迷雾民宿/正文/第1章.md
```

输出示例（`❌` 样本）：

```text
  汉字 536 | 句 35 段 15 | 对话行占比 35%
  句长 CV 0.51 | 最长均匀句串 3 | 短句占比 17% | 段落 CV 1.08
  感官通道 视觉
  把字句 0 | 口语标记 0.00/千字 | 重复强调 0 | 停顿段 0
  ! [缺少] longest_uniform_run: 连续 3 句长度相近（上限 2 句）——长-短-长或短-短-长，总之不要均匀
      来源：句式节奏档案 4.1「相邻三句的长度不要相近」
  ! [缺少] sensory_channels: 除视觉外没有任何感官通道（触觉/听觉/嗅觉/味觉/身体）
      来源：写作Agent 场景三维度·感知
  ...
```

`--target` 不需要传（字数归 `check_draft` 管）；本工具只回答「这一章的**人味和节奏**够不够」。

## draft_metrics 指标与规则来源

每条阈值都对齐对应规则的「门禁」原文，不自行发明标准：

| 指标 | 方向 | 规则来源 |
|:-----|:-----|:---------|
| 长度相近句串（整串跨度，非两两相邻差） | 缺少 | `句式节奏档案` 4.1「相邻三句的长度不要相近」 |
| 极短句数量（≤5 字） | 缺少 | `句式节奏档案` 4.1「还差一点。（极短，强调）」 |
| 连续同长度短段 | 缺少 | `writing-execution-map` 段落与句子 |
| 连续等长对话（通篇一问一答） | 缺少 | `写作Agent` Step 4 |
| 感官通道覆盖（视觉之外） | 缺少 | `写作Agent` 场景三维度·感知 |
| 口语标记密度（每千字） | 缺少 | `human-linguistics/SKILL.md` 原则 1 |
| 重复强调 / 叠词 | 缺少 | `语病诊断手册` 2.11「全文没有一个词是重复的 → 违规」 |
| 「把」字句（排除量词与器物名） | 缺少 | `句式节奏档案` 4.4 |
| 停顿段（不推进剧情的呼吸段） | 缺少 | `语病诊断手册` 2.7 |
| 段尾盖章总结 | 出现 | `语病诊断手册` 2.8 |
| 完整动作链（然后/接着/于是） | 出现 | `语病诊断手册` 2.3 |
| 情感标签（感到/充满 + 情感词） | 出现 | `语病诊断手册` 2.4 |
| 叙述内因果连接词 | 出现 | `语病诊断手册` 2.5 |
| 清单式环境罗列（数词+量词 ≥3） | 出现 | `语病诊断手册` 2.6 |
| 多余时间副词（正在/正准备/刚要） | 出现 | `语病诊断手册` 2.9 |
| 叙述内精确数值+单位 | 出现 | `human-linguistics/SKILL.md` 原则 2 |

**仅报告、不作门禁**：句长变异系数、段落变异系数、短句占比、对话行占比。
规则原文给的是「相邻三句不要相近」这类**串**判据，不是方差判据 —— 这些数字用于人工读报告，
不参与告警，避免把「我发明的阈值」伪装成「项目既有的标准」。

## 校准样本

`test/fixtures/draft_ai_flavor.md` 与 `test/fixtures/draft_human.md` 是**同一段剧情、同一篇幅**的两个版本，
用于验证指标确实能区分好坏（而不是「有一堆数字但分不出高下」）。当前结果：

| 样本 | `check_draft` | `draft_metrics` |
|:-----|:--------------|:----------------|
| `draft_ai_flavor.md` | 6 warn（判定式短句 ×2、段落超长 ×4） | **13 warn + 1 info**（加法 7 项全中，减法 7 项全中） |
| `draft_human.md` | **0 warn** | **0 warn / 0 info** |

两个工具抓的内容**不重叠**（`test_draft_metrics.py::test_two_tools_are_complementary_not_duplicated`
断言后者的核心指标在前者源码里根本不存在）。

阈值是**规则推导 + 这两个对照样本校准**得出的，**尚未用成品稿做统计校准**。
拿到真实章节后应回看阈值并在此处记录实测分布。

## 性能

`_longest_uniform_run` 朴素实现是 O(n²)，整本级（30 万字 ≈ 1.2 万句）要十几秒。
现在带两条剪枝（必要条件 + 剩余长度），实测：

| 场景 | 句数 | 朴素 | 剪枝 |
|:-----|-----:|-----:|-----:|
| 单章 3000 字 | 138 | 1.9 ms | 0.1 ms |
| 10 章 3 万字 | 1262 | 171 ms | 0.4 ms |
| 整本 30 万字 | 12472 | 14.1 s | **4.5 ms** |

剪枝不改变语义 —— `test_draft_metrics.py::TestPruningEquivalence` 用随机 + 结构化数据
与朴素实现**逐位对拍**，并有一条 1.2 万句的耗时回归断言。

## check_draft 用法

```bash
# 单章
python -m agent_core.check_draft projects/迷雾民宿/正文/第1章.md

# 整个项目（递归找 正文/*.md）
python -m agent_core.check_draft projects/迷雾民宿

# 带目标字数、输出 JSON、把 warn 也当失败
python -m agent_core.check_draft projects/迷雾民宿 --target 2500 --json --strict
```

Makefile 入口：

```bash
make check-draft DRAFT=projects/迷雾民宿/正文/第1章.md
```

退出码：`0` 无 error；`1` 存在 error（`--strict` 时 warn 也算）。`--allow-empty` 在 `projects/` 为空时返回 `0`，供 CI 使用。

CI 已经跑起来了（`.github/workflows/ci.yml` 的 `check-draft` job，对两个工具都跑一次）；
审稿清单的「表零A / 表零B」与交付清单的「机器预检」行都以它们为准。

## state 用法

把跨会话必须存活的运行时状态落到 `.harness/state/runtime.json`。

**为什么需要它**：`.harness/rules/subagent-runtime.md` 定义的挂起恢复、`pack-recommendation.md` 定义的开书状态机（S0–S5），此前只存在于对话上下文里——全仓库 61 处引用，**一个持久化载体都没有**。会话一断、上下文一压缩，恢复点就没了，整套机制悬空。

```bash
python -m agent_core.state show                      # 当前状态 + 恢复栈（LIFO）
python -m agent_core.state set stage S3
python -m agent_core.state set selected_topic "<题材>"
python -m agent_core.state push-resume R1 "查知识包"
python -m agent_core.state pop-resume                # 栈式恢复，与嵌套挂起语义一致
```

`--file` 是全局选项，必须放在子命令**之前**（测试与 CI 用它指向临时路径）。写入是原子的（先写 `.tmp` 再 `replace`）；文件损坏时先备份成 `runtime.corrupt.json` 再重建，不静默丢数据。

## 检查项与规则来源

每条检查项都能追溯到仓库里的既有规则，脚本不自定义标准：

| 检查项 | 级别 | 规则来源 |
|:-------|:-----|:---------|
| 正文路径符合 `projects/{项目}/正文/` | error | `rules/maps/draft-output-map.md` |
| T0 禁句 `不是X，是Y`（叙述中） | error | `human-linguistics/rules/语病诊断手册.md` 2.14 |
| T0 禁句（对白中） | info | 同上（对白允许少量） |
| 绝对禁用词：赋能 / 抓手 / 底层逻辑 | error | 语病诊断手册 2.12 |
| ★★★ 高危指纹词 | warn | 语病诊断手册 2.12 |
| 其余指纹词（迭代/闭环/复盘…） | warn | 语病诊断手册 2.12 |
| AI 废话短语 | warn | `参考_AI人性化正则规则.md` 8.1 |
| 进行病（进行/实施/做出/采取） | warn | 语病诊断手册 2.13 |
| 身份重复标签（作为/身为…的） | warn | 语病诊断手册 2.10 |
| 判定式短句（也就是说/这意味着…） | warn | 语病诊断手册 2.14 |
| 连续两段以过渡词开头 | warn | 语病诊断手册 2.1 |
| 单段 > 60 字 / 单句 > 45 字 | warn | `rules/maps/writing-execution-map.md` |
| 算式独立成行 | warn | `cases/feedback/2026-09-24-数字生硬.md` |
| ASCII 引号 / 半角省略号与破折号 | warn | `参考_AI人性化正则规则.md` 5 |
| 字数偏离目标 | warn | `rules/maps/draft-output-map.md` |

系统面板 `【…】`、代码块、Markdown 标题与表格会被屏蔽，不参与判定。

## 修改约定

改检查项时同步改 `test/test_check_draft.py` / `test/test_draft_metrics.py`。
规则文件是唯一真源——如果规则变了，这里要跟着变，而不是反过来。

**加新指标前先问一句**：这条能不能被机器判定？
能 → 加进 `draft_metrics.py` + `chapter-required-reading.md` 第二节表零B；
不能（要判断语义、人设、留白好坏）→ 留在 Markdown，不要硬凑一个统计量。

提交前本地过一遍 CI 的同等检查：

```bash
python -m pytest agent_core/test/
python -m pyflakes agent_core/
python -m pycodestyle agent_core/ --max-line-length=120 --ignore=E402,W503
python -m agent_core.check_draft projects --allow-empty
python -m agent_core.draft_metrics projects --allow-empty
```

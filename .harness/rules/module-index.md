# 总编模块索引

> 用途：总编 Agent 按任务找到对应专业 Agent、skill、规则和 L0 项目上下文。
> 注意：本文件是索引，不承载具体规则细节。

---

## 专业 Agent

| Agent | 职责 | 定义文件 |
|:------|:-----|:---------|
| 上下文 Agent | 状态追踪、伏笔管理、上下文打包、信息中枢 | `.harness/agents/上下文Agent.md` |
| 规划 Agent | 剧情构思、设定扩展、反转/钩子设计 | `.harness/agents/规划Agent.md` |
| 写作 Agent | 基于大纲、约束和上下文包生成正文 | `.harness/agents/写作Agent.md` |
| 审稿 Agent | 调用各审查子模块，执行全面或专项审查 | `.harness/agents/审稿Agent.md` |
| 短剧编剧 Agent | 小说改编 AI 短剧，产出人物提示词与 10s 分镜脚本 | `.harness/agents/短剧编剧Agent.md` |
| 短视频编剧 Agent | 话题 → 抖音短视频文案（故事脚本），产出开头钩子 / 起承转合 / 旁白·对白·字幕 | `.harness/agents/短视频编剧Agent.md` |
| 短视频分镜 Agent | 短视频文案 → 竖屏分镜镜头（每镜 11 字段 + H3 出片提示词），复用短剧摄影词汇 | `.harness/agents/短视频分镜Agent.md` |

---

## 审查与创作模块

| 题材/用途 | 子模块 skill | 说明 |
|:----------|:-------------|:-----|
| 数据化降临/游戏异界/副本流 | `.harness/skills/game-datafied` | 战斗描写规范、数值体系、装备/经验/战力逻辑 |
| 通用·降低 AI 语感 | `.harness/skills/human-linguistics` | AI 式语病诊断、语感词典、句式节奏、轻量去 AI 味 |
| 通用·情节一致性 | `.harness/skills/plot-review` | 角色行为一致性、时间线、伏笔、信息边界、状态一致 |
| 通用·节奏/爽点 | `.harness/skills/rhythm-review` | 高潮间隔、钩子密度、爽点分布、阅读体验体感 |
| 通用·创作灵感 | `.harness/skills/plot-ideation` | 剧情构思、设定扩展、反转/钩子、多方向推演 |
| 短剧·H3 视频提示词 | `.harness/skills/h3-prompt-writing` | MiniMax H3 原生格式英文权威原文（T2VA/I2VA/FL2VA/L2VA/Ref2VA + references/base-en.txt、ref-en.txt）。**硬门禁：写任何 H3 提示词前必读**（先 SKILL.md 判模式，再读对应 references/） |
| 全局·知识包 | `.harness/knowledge` | 随项目自带知识包、MCP 下载知识包、RAG 可检索资料。**已装包总览与选包指引见 `.harness/knowledge/pack-catalog.md`**（题材→包、重叠优先级、分类映射、维护命令） |

---

## 常用规则文件

| 需求 | 加载文件 |
|:-----|:---------|
| 去 AI 味 | `.harness/skills/human-linguistics/rules/去AI味最小修改指南.md` |
| 查语病 | `.harness/skills/human-linguistics/rules/语病诊断手册.md` |
| 句式节奏 | `.harness/skills/human-linguistics/rules/句式节奏档案.md`（4.1 / 4.4 / 4.5 / 4.6 的可判定部分已由 `draft_metrics` 接管） |
| 角色关系 | `.harness/skills/plot-review/rules/角色关系金字塔.md` |
| 角色知识边界 | `.harness/skills/plot-review/rules/角色知识边界.md` |
| 状态一致性 | `.harness/skills/plot-review/rules/状态一致性补充清单.md` |
| 大纲质量 | `.harness/skills/plot-review/rules/大纲质量评估清单.md` |
| 阅读体验 | `.harness/skills/rhythm-review/references/阅读体验与章节润色检查.md` |
| 写前准备 | `.harness/skills/plot-ideation/references/章节写前准备清单.md` |
| 正文机器预检·减法 | `agent_core/check_draft.py`（「不该出现什么」：禁句/指纹词/段落超长…；`make check-draft`；审稿清单**表零A**、交付清单「机器预检」行都用它） |
| 正文机器预检·加法 | `agent_core/draft_metrics.py`（「应该出现什么」：节奏均匀串/极短句/感官通道/口语密度/重复强调缺失…；`make draft-metrics`；审稿清单**表零B**）。**只跑减法会漏掉整类问题**，两个必须成对 |
| 运行时状态落盘 | `agent_core/state.py`（挂起恢复栈、开书阶段 S0–S5、已锁定题材/平台/知识包 → `.harness/state/runtime.json`；`python -m agent_core.state show`） |
| **单章必读索引** | `.harness/rules/maps/chapter-required-reading.md`（**写章/审稿的默认加载集合入口**，避免预读全部规则；其余规则按触发条件加载） |
| 正文落盘门禁 | `.harness/rules/maps/draft-output-map.md` |
| **成稿交付清单** | `.harness/rules/maps/delivery-output-map.md`（**每次成稿必附 ①执行流程清单 + ②规则坚持表**） |
| 短剧规格与提示词公式 | `.harness/rules/maps/short-drama-adaptation-map.md` |
| 短剧摄影词汇库 | `.harness/rules/maps/short-drama-prompt-glossary.md` |
| MiniMax H3 视频提示词格式 | `.harness/rules/maps/short-drama-h3-prompt-format.md`（完整规范；**写 H3 前必读**；权威英文原文见 `.harness/skills/h3-prompt-writing/`） |
| 章节期待链 | `.harness/rules/maps/planning-continuity-map.md` |
| 场景三维度织入 | `.harness/rules/maps/writing-execution-map.md` |
| 对话权力与议程 | `.harness/rules/maps/writing-execution-map.md` |
| 最小记忆包 | `.harness/rules/maps/state-tracking-map.md` |
| 章节质量检查 | `.harness/rules/maps/quality-check-map.md` |
| 审稿强制执行清单 | `.harness/rules/maps/review-execution-checklist.md`（审稿 Agent 每次审查先跑表零A/表零B 机器预检，再逐行执行表一~表七，含分镜脚本专项） |
| 状态追踪协议 | `.harness/rules/maps/state-tracking-map.md` |
| 人物视角边界 | `.harness/rules/maps/perspective-boundary-map.md` |
| 叙事视角配置 | `.harness/rules/maps/perspective-boundary-map.md` |
| 短剧分镜脚本模板 | `.harness/rules/maps/short-drama-script-template.md`（每镜 11 字段 + 人物卡 9 字段 + 双 H3 出片 + 出片细化包通用空模板） |
| 短视频文案规格 | `.harness/rules/maps/short-video-story-map.md`（抖音短视频规格 / 3 秒钩子 / 起承转合 / 话题拆解 / 文案形态 / 落盘约定） |
| **反馈追踪流程** | `.harness/rules/反馈追踪流程.md`（**反馈追踪机制的唯一实体源**：核心流程、触发标准、3 次触发规则更新、文件命名与 `status` 字段、身份感知解读、模板位置；`cases/feedback/README.md` 只留目录说明） |
| 通用编辑规范 | `.harness/rules/editorial-standards.md` |
| 审稿输出格式 | `.harness/rules/审稿输出模板.md`（审稿报告的标准版式；表零A–D + 表一–七 的呈现方式） |
| 用户分层适配 | `.harness/rules/用户身份适配指南.md`（Lv.1 零基础 / Lv.2 老书虫 / Lv.3 资深作者；总编 Agent Step 0.5 的支撑文件） |
| **挂起恢复协议** | `.harness/rules/subagent-runtime.md`（可挂起临时任务的隔离与恢复；落盘要求见第 5 节 → `agent_core/state.py`） |

---

## 规则 Map

| Map | 作用 | 主要使用者 |
|:----|:-----|:-----------|
| `.harness/rules/maps/planning-continuity-map.md` | 三层期待、小纲四步法、线索热度、章尾钩子 | 规划 Agent |
| `.harness/rules/maps/writing-execution-map.md` | 场景三维度织入、对话议程、小节偏短诊断、段落句子控制 | 写作 Agent |
| `.harness/rules/maps/state-tracking-map.md` | 最小记忆包、状态快照、伏笔、线索热度 | 上下文 Agent |
| `.harness/rules/maps/quality-check-map.md` | 通用质量门禁、长篇/短篇专项、五维评分 | 审稿 Agent / 写作 Agent |
| `.harness/rules/maps/perspective-boundary-map.md` | 人物视角、叙事视角、角色/NPC 信息边界 | 规划 Agent / 写作 Agent |
| `.harness/rules/maps/draft-output-map.md` | 正文落盘、项目骨架初始化、正文文件定位、写作恢复 | 总编 Agent / 写作 Agent / 上下文 Agent |
| `.harness/rules/maps/chapter-required-reading.md` | 单章必读索引：默认加载集合 + 机器已接管清单 + 按需触发条件 | 写作 Agent / 审稿 Agent |
| `.harness/rules/maps/short-drama-adaptation-map.md` | 短剧规格、镜头字段、提示词公式、三幕钩子、人物提示词、落盘约定 | 短剧编剧 Agent |
| `.harness/rules/maps/short-drama-prompt-glossary.md` | 摄影提示词词汇库（光源/光线/景别/构图/运镜/风格选词） | 短剧编剧 Agent |
| `.harness/rules/maps/short-drama-h3-prompt-format.md` | H3 视频提示词完整写作规范（模式判定/镜头语法/运镜/说话人/对白铁律/声音字段边界/Ref2VA 六段式/中文适配/自检） | 短剧编剧 Agent |
| `.harness/rules/maps/short-drama-script-template.md` | 短剧分镜脚本通用空模板（11 字段/人物卡/双 H3 出片/出片细化包），改编时套用 | 短剧编剧 Agent |
| `.harness/rules/maps/short-video-story-map.md` | 抖音短视频文案规格、3 秒钩子、起承转合结构、话题拆解、文案形态、落盘约定 | 短视频编剧 Agent / 短视频分镜 Agent |

---

## 知识包缺口协调

当规划、写作、审稿或上下文 Agent 提示缺少题材、平台风格、去 AI 化或写作方法参考时，总编 Agent 不要让下属 Agent 硬编规则。

用户不知道写什么、没有明确目标平台时，总编 Agent 不要默认只按起点口味找素材。新手优先参考番茄，再补起点对照；起点适合长线结构和设定纵深，番茄适合新手观察大众题材、快节奏和强钩子。

平台选择是任务参数，不是 Agent 默认身份。未确认平台时，总编和下属 Agent 都保持跨平台中立。

处理流程：

```text
发现缺口
  -> 按 .harness/knowledge/pack-recommendation.md 给用户候选知识包
  -> 用户确认
  -> MCP 安装 / RAG 重建
  -> 按 .harness/rules/subagent-runtime.md 恢复原任务
```

候选话术：

```text
检测到当前任务缺少 {题材/风格/审稿} 参考包。
可选素材包：
1. {pack_id}：{name}（匹配原因）
2. {pack_id}：{name}（相近参考）
你要启用哪一个？未确认前我不会强制使用。
```

---

## L0 项目上下文索引

| 文件 | 用途 | 使用时机 |
|:-----|:-----|:---------|
| `.harness/current-project.md` | 当前项目指针 | 每次启动 Step -1 时读取 |
| `.harness/project-templates/模板-数据化降临.md` | 数据化降临题材创作约束 | 项目设置为该题材时加载 |
| `.harness/project-templates/模板-游戏入侵现实-版本更新预告.md` | 游戏入侵现实、版本更新预告、灰度异常题材创作约束 | 项目设置为该题材时加载 |
| `.harness/project-templates/模板-末世小黑屋.md` | 末世小黑屋题材创作约束 | 项目设置为该题材时加载 |

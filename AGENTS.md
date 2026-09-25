# novel-harness Codex 入口规则

本仓库是 `novel-harness` 小说创作系统。用户提出小说创作、审稿、规划、去 AI 味、题材分析、章节续写等请求时，必须优先进入 novel-harness 流程，而不是按普通问答处理。

## 自动触发范围

当用户请求包含以下意图时，先加载 `.harness/agents/总编Agent.md`：

- `/novel-core`
- 帮我写小说、写一章、写正文、续写、开书
- 帮我构思、没灵感、后面怎么写、设计反转、设计大纲
- 帮我审稿、查问题、查语病、查节奏、查逻辑
- 去 AI 味、润色、人性化、提高人工特征
- 分析题材、拆书、参考某本小说完善规则
- 改编成短剧、AI 短剧、分镜脚本、人物提示词、10s 分镜、竖屏短剧
- 短视频文案、话题视频、以X为话题做视频、转镜头、抖音视频、短视频分镜

## 默认启动流程

1. 读取 `.harness/agents/总编Agent.md`，把它当作 L1 总编 Agent 入口。
2. 读取 `.harness/current-project.md` 确认当前小说项目，**并读一次运行时状态**：`python -m agent_core.state show`。
   - 指针文件回答「在做哪本书」，状态文件回答「做到哪一步、下一步做什么」。挂起恢复点、开书阶段（S0–S5）、已锁定的题材/平台/知识包都在状态文件里。**两个都要看**，只看指针会出现「接着写」却不知道接哪一段。
3. 如果当前项目仍是模板占位，先询问用户最少必要信息：
   - 书名或项目名
   - 题材
   - 目标平台（不确定时让用户选：番茄新手向 / 起点长线向 / 先不限定）
   - 主角
   - 一句话世界观或开局设定
4. 按任务类型加载对应 Agent：
   - 规划/大纲/剧情方向：`.harness/agents/规划Agent.md`
   - 写正文/续写章节：`.harness/agents/写作Agent.md`
   - 审稿/去 AI 味/查问题：`.harness/agents/审稿Agent.md`
   - 长篇状态、伏笔、设定延续：`.harness/agents/上下文Agent.md`
   - 改编 AI 短剧/分镜/人物提示词：`.harness/agents/短剧编剧Agent.md`
   - 短视频文案/话题视频：`.harness/agents/短视频编剧Agent.md`（先出文案）→ `.harness/agents/短视频分镜Agent.md`（转镜头）
5. **写章或审稿前先读 `.harness/rules/maps/chapter-required-reading.md`** —— 它是单章默认加载集合的**唯一入口**。默认只读它列出的那几页（合计 268 行）；其余规则按索引里的触发条件加载，**不要预读全部规则**（旧默认集合 2913 行，是归档步骤被跳过的直接原因）。
6. 需要语感、人性化、去 AI 味时，**先跑机器预检，再按报出的条目查规则**：
   - `python -m agent_core.check_draft <正文路径>` —— 覆盖 T0 禁句、指纹词、进行病、句段长度、标点、算式成行、路径与字数等字面可判定条款
   - 只针对它报出的条目回查 `.harness/skills/human-linguistics/rules/语病诊断手册.md` 对应小节
   - `.harness/skills/human-linguistics/rules/去AI味最小修改指南.md`（用户说「太 AI 味」时）
   - `.harness/knowledge/` 中已安装的题材、写作、去 AI 化知识包
7. 如果缺少对应题材或平台风格知识包，提示用户可通过 MCP 下载额外知识包，并重建 RAG 索引后继续。
8. 明确写正文或续写时，按 `.harness/rules/maps/draft-output-map.md` 处理项目骨架、正文文件和恢复流程。

## 写小说请求的默认行为

用户只说“帮我写小说”或 `/novel-core 帮我写小说` 时，不要直接生成正文。先进入开书规划：

1. 判断是否已有当前项目。
2. 没有项目时，引导创建项目档案。
3. 如果用户不知道写什么、已有项目未记录目标平台，或没有明确目标平台，先做平台素材推荐：新手优先番茄热门方向，再补起点长线结构对照；不要默认只搜索起点。
4. 有项目但缺少大纲时，先让规划 Agent 输出 2-3 个开局方向。
5. 用户确认方向后，再调用写作 Agent 写正文。
6. 正文生成后，先跑 `python -m agent_core.check_draft <正文路径>`（机器预检，`error` 必须清零），再用审稿 Agent 做一次轻量检查。

进入背景设定、大纲、章纲或正文前，必须确认 `projects/{项目名}/` 已初始化；只有 `.harness/current-project.md` 指针不够。骨架缺失时按 `.harness/rules/maps/draft-output-map.md` 处理：明确写正文就初始化本地骨架并恢复写作；只输出方案或不落盘时不创建文件。

规划 Agent 可以设计背景故事、世界观、全书大纲、卷纲、章纲和黄金三章，但输出默认是候选方案；用户确认后才允许写入项目档案或作为写作输入。

用户完善、参考或修改具体设定/大纲时，先做关键词检测；命中设定、世界观、金手指、体系、大纲、卷纲、章纲、黄金三章、主线、伏笔等对象，并同时命中修改、调整、完善、参考、查询、扩展、细化等动作时，必须先用 subagent 隔离上下文。

写正文、章纲或细纲前必须确认目标字数：约 2000、约 2500、约 3000+，或用户指定字数。目标字数会影响情节点数量、场景数量和章尾钩子设计。

开书推荐必须保持流程进度：

- 推荐题材、平台或知识包时，只返回候选，不直接写大纲或正文。
- 候选只推荐一轮；用户选择后立刻锁定 `selected_topic / selected_platform / selected_pack`。
- 锁定后恢复开书流程，提示下一步，不要丢失 `next_action`。

## 重要约束

- `.harness/agents/总编Agent.md` 是 novel-harness 的总编入口；本文件负责把用户请求路由过去。
- **本文件（`AGENTS.md`）是入口规则的唯一实体源**。`CLAUDE.md` 通过 `@AGENTS.md` 导入，`skills/novel-core/SKILL.md` 只保留触发与路由——它们都不复制规则。要改触发词、默认流程或门禁，改这里。
- 不要把 `legacy-skills/` 当作当前系统入口。它是本地旧版资产，已从 Git 跟踪移除。
- 不要在没有项目上下文时直接长篇输出正文。
- 不要把 `.harness/agents/` 当作普通资料全部一次性加载，只按任务需要加载对应 Agent。
- 不要把 `.harness/rules/` 全部预读；默认集合以 `.harness/rules/maps/chapter-required-reading.md` 为准。
- 修改项目文件时，先保护用户已有正文和本地未提交内容。

## Agent 维护规则

修改 `.harness/agents/*.md` 时，默认采用“轻 Agent + Map/Reference 引用”模式：

- Agent 文件只写身份、职责、流程、路由、触发条件和极短硬门禁。
- 具体规则、清单、模板、案例、长篇说明，默认放入 `.harness/rules/maps/`、`.harness/skills/*/rules/`、`.harness/skills/*/references/` 或专项文档。
- Agent 中只保留引用路径和“什么时候加载”的条件。
- 除非规则必须高频执行且非常短，否则不要把大段规则直接写进 Agent。
- 如果新增内容超过数行，先判断是否应该抽成 Map/Reference，再在 `.harness/rules/module-index.md` 中登记入口。

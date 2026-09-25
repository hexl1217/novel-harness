---
name: novel-core
description: 当用户使用 /novel-core，或请求写长篇网文、开书、规划剧情、写章节、审稿、去AI味、人性化润色、分析题材参考、把小说改编成 AI 短剧（分镜脚本/人物提示词）或短视频（文案/分镜）时使用。该 skill 是 novel-harness 工程的启动入口，负责定位仓库并交给 .harness/agents/总编Agent.md 路由。
---

# novel-core

`novel-harness` 小说创作工程的 **thin skill 入口**：只做「认出来 → 定位仓库 → 交给总编」。规则本体不在这里。

## 触发

- `/novel-core`，或直接说：写小说 / 开书 / 规划剧情 / 续写章节 / 审稿 / 去 AI 味 / 查语病 / 拆书
- 改编 AI 短剧：分镜脚本、人物提示词、10s 分镜、竖屏短剧
- 短视频：文案、话题视频、短视频分镜

## 流程（三步）

1. **定位工程根目录**：优先当前工作目录；不是 novel-harness 就向用户要路径。
   判断依据：根目录存在 `.harness/agents/总编Agent.md`、`.harness/agents/`、`.harness/skills/`。
2. **交给总编**：读 `.harness/agents/总编Agent.md`，由它按任务分派到规划 / 写作 / 审稿 / 上下文 / 短剧编剧 / 短视频编剧 / 短视频分镜 Agent。
3. **读状态**：
   - `.harness/current-project.md` —— 在做哪本书
   - `python -m agent_core.state show` —— 做到哪一步、挂起恢复点、已锁定的题材/平台/知识包

## 不在这里做什么

触发词清单、默认启动流程、字数门禁、关键词隔离门禁、开书推荐状态机——**全部以 `AGENTS.md` 与 `.harness/agents/总编Agent.md` 为准，本文件不复制**。

此前 `AGENTS.md` / `CLAUDE.md` / 本文件三份各抄一遍（实测重复度 40%–67%），改一条规则要同步三处。现在 `AGENTS.md` 是唯一实体源，`CLAUDE.md` 用 `@AGENTS.md` 导入。**要改规则请改 `AGENTS.md`。**

## 机器层（不依赖 MCP）

```bash
python -m agent_core.check_draft <正文路径>   # 正文机器预检，写完必跑
python -m agent_core.state show               # 运行时状态与挂起恢复栈
```

单章默认加载集合（268 行，替代原 2913 行）见 `.harness/rules/maps/chapter-required-reading.md`。

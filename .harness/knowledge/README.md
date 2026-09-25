# knowledge 知识包层

`.harness/knowledge/` 是 novel-harness 的统一知识包目录，用来承载可被 RAG 检索的题材参考、去 AI 化规则、写作方法、平台风格和后续 MCP 下载的扩展资料。

它和 skill 内部的 `references/` 不同：

- `skills/**/references/`：某个 skill 自带的局部引用资料。
- `knowledge/`：贯穿整个项目、可按包安装和索引的全局知识库。

## 目录边界

```text
.harness/knowledge/
├── included/  # 随项目自带的公开知识包
├── packs/     # 知识包 manifest、版本和来源说明
├── remote/    # MCP 从服务器下载的知识包，本地目录，不上传 Git
├── pack-catalog.md         # 已装知识包总览与选包指引
├── pack-recommendation.md  # 写作前素材/知识包推荐规则
└── user/      # 用户私有知识包，本地目录，不上传 Git
```

## 写作前推荐规则

开书、设计故事背景、大纲、章节写作或需要专项审稿前，先按 `pack-recommendation.md` 推荐可选知识包。

核心边界：

- 只给选项，不替用户决定启用哪个题材包。
- 用户确认前，不安装、不启用、不强制套用任何知识包。
- 没有精准匹配时，只能给相近候选，并明确说明“相近，不是精准”。
- 用户选择暂不使用素材包时，继续使用通用写作规则。
- 知识包推荐会使用通用挂起恢复机制；安装和 RAG 重建完成后，恢复到挂起前的下一步继续执行。
- 知识包只在已确认的任务作用域内生效；除非用户确认，不写入项目长期设定。

subagent、临时任务挂起恢复与知识作用域隔离规则见：`../rules/subagent-runtime.md`

## 默认 RAG 策略

默认索引：

```text
.harness/knowledge/included/
.harness/knowledge/remote/   # 含 .md 与 .txt
.harness/skills/
.harness/project-templates/
docs/
```

默认不索引：

```text
projects/
rag/data/
.harness/knowledge/user/
```

`user/` 用于未来私有资料扩展，只有用户明确开启时才进入索引。

## 管理命令

```powershell
python rag/scripts/sync_packs.py list
python rag/scripts/sync_packs.py installed
python rag/scripts/sync_packs.py --manifest <manifest路径或URL> install <pack_id> --rebuild-index
```

`sync_packs.py` 是后续 MCP 知识包服务的本地执行层。MCP 只负责把 AI 工具调用转成这些本地动作。

## 知识包分类

- `deslop/`：去 AI 化、人性化、句式、语感、正则规则。
- `topics/`：题材包，例如全民求生、游戏数据化、电竞、修仙、都市、悬疑。
- `writing/`：写作技法，例如黄金三章、爽点、钩子、节奏、伏笔；以及经典写作理论与书目（`writing-craft-classics`）。
- `market/`：平台风格，例如番茄、起点、知乎短篇等。
- `cases/`：自写案例、修改前后对照、问题复盘。

## 已装包与选包指引

- 内置包 4 个，见 `packs/included.manifest.json`。
- 云端包 35 个，装在 `remote/`（本地包，不进 Git），覆盖玄幻仙侠、都市现实、悬疑刑侦、情感女频、末世求生、历史权谋、科幻赛博、游戏电竞、恐怖规则怪谈、短剧改编等主流方向，另有设定设计、表达润色、写作方法、流程与市场工具包。
- 按题材选包、重叠优先级、分类与检索映射：见 `pack-catalog.md`。
- 新增远程包后，需要在 `rag/src/normalizer.py` 的 `REMOTE_PACK_CATEGORY` 登记包名前缀，否则会落到默认分类。

## 版权边界

知识包只能放自写规则、拆解总结、授权资料和短句级自写示例。不要放未授权小说正文、平台章节原文或可替代原作阅读的大段摘录。

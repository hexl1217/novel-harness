# 知识包使用说明

知识包是 novel-harness 的全局参考资料层，用来给 RAG 提供题材、写法、去 AI 化、平台风格等可检索资料。

## 目录

```text
.harness/knowledge/
├── included/  # 随项目自带的知识包
├── packs/     # 知识包 manifest
├── remote/    # 远程下载知识包，本地使用，不上传 Git
└── user/      # 用户私有知识包，默认不索引，不上传 Git
```

## 当前内置包

- `deslop-basic`：去 AI 味基础规则。
- `webnovel-writing-basic`：黄金三章、章节结构、爽点和钩子。
- `survival-topic`：全民求生、庇护所、资源循环、天灾压迫题材。
- `writing-craft-classics`：写作技法经典书目与理论。

## 已装云端包

云端市场现有 35 个包，已全部装到 `.harness/knowledge/remote/`（本地目录，不进 Git）：

- 题材 19 个：玄幻仙侠、都市现实、悬疑刑侦、情感女频、末世求生、历史权谋、科幻赛博、游戏电竞、恐怖规则怪谈、短剧改编、同人、年代世情等。
- 写作方法 6 个、设定设计 4 个、表达润色 2 个、流程与市场 4 个。

按题材选包、重叠优先级、分类与检索映射，统一查 `.harness/knowledge/pack-catalog.md`。
未安装的机器按该文档第七节命令重装，并执行一次 `rebuild-index`。

## 写作前素材推荐

开书、设计故事背景、大纲或正式写作前，总编 Agent 会先根据用户方向推荐知识包。用户方向明确时，优先找对应包；没有精准匹配时，只给出相近选项。

重要边界：

- 只提供选项，不在用户确认前强制启用任何题材包。
- 本地已安装不等于自动启用。
- 相近知识包只能作为参考，不能冒充精准题材包。
- 用户可以选择暂不使用知识包，直接用通用写作规则继续。
- 推荐知识包会调用通用挂起恢复机制；安装、下载和重建 RAG 完成后，必须恢复到挂起前的下一步继续执行。

推荐规则见：`.harness/knowledge/pack-recommendation.md`

## 启用前先安装依赖

如果要重建 RAG 索引，必须先给当前正在使用的 Python 安装依赖：

```powershell
python -m pip install -r rag/requirements.txt
```

注意要使用同一个 Python。比如你用下面这个命令安装知识包：

```powershell
python rag/scripts/sync_packs.py --manifest <远程manifest地址> install topic-xuanhuan --rebuild-index
```

那么依赖也要安装到这个 `python` 对应的环境里。否则重建索引时可能会报：

```text
ModuleNotFoundError: No module named 'numpy'
```

## 常用命令

```powershell
python -m pip install -r rag/requirements.txt
python rag/scripts/sync_packs.py list
python rag/scripts/sync_packs.py list --include-remote
python rag/scripts/sync_packs.py installed
python rag/scripts/build_index.py
```

使用云端市场前，先在项目根目录的 `.env` 里配置市场地址（该文件已被 `.gitignore` 忽略，不会被提交）：

```text
NOVEL_HARNESS_REMOTE_MANIFEST=<你的 manifest 地址>
```

也可以改用环境变量注入，适合容器与 CI 场景。仓库不内置任何市场地址；未配置时命令会直接提示配置方式，不会静默失败。

安装云端知识包：

```powershell
python rag/scripts/sync_packs.py list --include-remote
python rag/scripts/sync_packs.py install topic-xuanhuan --rebuild-index
```

要临时使用其他 manifest，可用 `--manifest <远程manifest地址>` 覆盖，注意该参数需放在子命令之前。

## 版权边界

知识包只放自写规则、拆解总结、授权资料和短句级自写示例。不要放未授权小说正文、平台章节原文或可替代原作阅读的大段摘录。

## RAG 策略

默认索引：

- `.harness/knowledge/included/**/*.md`
- `.harness/knowledge/remote/**/*.md`
- `.harness/skills/**/references/*.md`
- `.harness/skills/**/rules/*.md`
- `.harness/project-templates/*.md`

默认不索引：

- `.harness/knowledge/user/**`
- `projects/**`
- `rag/data/**`

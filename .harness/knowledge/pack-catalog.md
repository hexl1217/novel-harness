# 知识包总览与选包指引

> 用途：总编 Agent 在开书、设定、大纲、正文、审稿前按 `pack-recommendation.md` 推荐知识包时先查本表；用户也可以直接按本表点单。
> 收录：`included/` 随项目自带的 4 个包 + `remote/` 本地已装的 35 个云端包。
> 边界：`remote/` 是本地包、**不进 Git**；换机器后按第七节命令重装即可。

---

## 一、怎么用

1. 按「主流题材 → 包」定位主包；同一题材有多个包时，按第四节定优先级，主包优先、备包补充。
2. 选定后按 `pack-recommendation.md` 的 S1–S3 锁定 `selected_pack`，再进大纲或正文。
3. 包只作本轮参考，不作为项目长期设定写入；要固化必须回总编确认。
4. 命中不到题材时不要硬套相近包，先按第七节去云端市场找，或走自建包。

---

## 二、题材包（19 个 · 主力参考）

| 方向 | 主包 id | 名称 | 篇数 | 什么时候用它 |
|:-----|:--------|:-----|:-----|:-------------|
| 玄幻仙侠修真 | `library-topic-xuanhuan-xianxia` | 玄幻仙侠题材资料包 | 25 | 渡劫飞升、炼丹炸炉、废柴逆袭、拍卖会、灵气复苏、动物修仙等具体桥段 |
| 玄幻（流程骨架） | `topic-xuanhuan` | 玄幻小说题材参考包 | 10 | 需要「创意→设定→框架→章节→反馈」整套流程模板时 |
| 奇幻西幻异世界 | `library-topic-fantasy-western` | 奇幻西幻题材资料包 | 30 | 魔法体系、异世界、西幻背景 |
| 都市现实 | `library-topic-urban-realistic` | 都市现实题材资料包 | 40 | 职场、娱乐圈、直播、现实向都市 |
| 悬疑刑侦推理 | `library-topic-mystery-detective` | 悬疑刑侦推理题材资料包 | 23 | 刑侦、法医、推理办案 |
| 恐怖灵异·克苏鲁 | `library-topic-horror-weird` | 恐怖灵异与规则怪谈资料包 | 39 | 灵异、克苏鲁、民俗恐怖 |
| 规则怪谈·副本 | `topic-rule-horror` | 规则怪谈题材参考包 | 30 | 规则设定、副本、恐怖氛围、推理逻辑 |
| 末世废土求生 | `library-topic-apocalypse-survival` | 末世废土求生题材资料包 | 11 | 废土、避难所经营、资源压迫（全民求生另有内置 `survival-topic`） |
| 科幻赛博 | `library-topic-scifi-cyber` | 科幻赛博题材资料包 | 46 | 赛博朋克、机甲、星际、AI |
| 游戏电竞体育 | `library-topic-game-sports` | 游戏电竞体育题材资料包 | 23 | 游戏异界、职业电竞、公会战、体育竞技 |
| 历史古代权谋 | `library-topic-history-power` | 历史古代权谋题材资料包 | 17 | 权谋、宫斗、古代朝堂 |
| 多子多福·后宫 | `library-topic-duoziduofu` | 多子多福题材资料包 | 177 | 子嗣系统、后宫、种田流（本库体量最大的包） |
| 同人 IP | `library-topic-fanfic-ip` | 同人 IP 创作资料包 | 22 | 借原著世界观、CP 线、同人改编 |
| 年代·四合院 | `topic-siheyuan` | 情满四合院题材参考包 | 10 | 年代感、生活流、大院群像 |
| 情感女频关系 | `library-topic-romance-female` | 情感女频关系题材资料包 | 83 | 替身、追妻、豪门、关系线结构 |
| 狗血女文 | `topic-gouxue-nvwen` | 狗血女文题材参考包 | 20 | 虐点、反转、催泪、冲突升级 |
| 世情文 | `topic-shiqing` | 世情文题材参考包 | 10 | 现实情感、家庭邻里、人物关系 |
| 知乎短篇 | `topic-zhihu-short` | 知乎短篇题材参考包 | 20 | 短篇反转、付费卡点、快节奏、第一人称 |
| 短剧影视改编 | `library-topic-short-drama-media` | 短剧影视改编题材资料包 | 11 | 短剧改编、影视化、分镜配合（对接本仓短剧编剧 Agent） |

篇数为包自报数量，仅用于判断体量，不等同于可直接引用的条目数。

---

## 三、方法与工具包（16 个）

### 写作方法（`library-writing-*` / `webnovel-*`）

| 包 id | 名称 | 篇数 | 什么时候用它 |
|:------|:-----|:-----|:-------------|
| `library-writing-outline-pacing` | 大纲结构与节奏设计包 | 39 | 大纲结构、节奏、黄金三章 |
| `library-writing-character-relations` | 人物角色与关系设计包 | 32 | 人物档案、反派、群像区分、角色弧光、语气模仿 |
| `library-writing-action-scenes` | 场景动作与战斗写作方法包 | 18 | 战斗、战争、对话优化、动作细化 |
| `webnovel-setting-framework` | 网文设定与大纲框架包 | 26 | 世界观、等级、金手指、黄金三章的框架化输入 |
| `webnovel-creative-planning` | 网文创意与立项规划包 | 9 | 开书创意发散、题材卖点定位 |
| `webnovel-drafting-polish` | 网文正文创作与润色包 | 23 | 章节创作、修订润色、状态管理、AI 写作反检测 |

### 设定设计（`library-design-*`）

| 包 id | 名称 | 篇数 | 什么时候用它 |
|:------|:-----|:-----|:-------------|
| `library-design-worldbuilding` | 世界观设定设计包 | 12 | 地图、文明、语言、副本世界观 |
| `library-design-system-cheat` | 系统金手指设定设计包 | 10 | 系统面板、技能树、任务与惩罚机制 |
| `library-design-rules-mechanics` | 规则机制设定设计包 | 7 | 规则、机制、副本、数值平衡 |
| `library-design-factions-resources` | 组织势力与资源设定包 | 7 | 势力组织、资源循环、种田 |

### 表达润色（`library-polish-*`）

| 包 id | 名称 | 篇数 | 什么时候用它 |
|:------|:-----|:-----|:-------------|
| `library-polish-emotion-sensory` | 情绪心理与感官表达润色包 | 38 | 情绪、心理、感官、张力不够时找手段 |
| `library-polish-language-style` | 语言风格与修辞润色包 | 19 | 文风、修辞、氛围 |

### 流程与市场（`library-workflow-*` / `webnovel-analysis-*` / `library-writing-market-*`）

| 包 id | 名称 | 篇数 | 什么时候用它 |
|:------|:-----|:-----|:-------------|
| `library-workflow-writing-checklists` | 写作工具与检查表包 | 9 | 卡文救援、伏笔回收检查、完稿检查清单 |
| `library-workflow-agent-pipeline` | 创作流程 Agent 工具包 | 5 | 首章/续章/摘要/状态/检索关键词的专家提示词 |
| `library-writing-market-concept` | 创意立项与市场工具包 | 17 | 选题评估、书名与简介、首秀数据诊断 |
| `webnovel-analysis-commercial-tools` | 网文数据分析商业化与辅助工具包 | 33 | 阅读体验与质量评分、读者反馈、拆书、商业化 |

---

## 四、重叠与优先级

| 重叠主题 | 主包 | 备包 | 规则 |
|:---------|:-----|:-----|:-----|
| 玄幻 | `library-topic-xuanhuan-xianxia` | `topic-xuanhuan` | 要桥段、流派、具体写法用主包；要全流程模板才翻备包 |
| 规则怪谈 / 恐怖 | 规则设定类用 `topic-rule-horror`<br>灵异克苏鲁类用 `library-topic-horror-weird` | 互为补充 | 按「规则解谜」还是「恐怖氛围」分派；同一次任务只选一个主包 |
| 求生 | 全民求生 / 迷雾木屋 / 庇护所用内置 `survival-topic` | `library-topic-apocalypse-survival` | 内置包是规则卡，远程包是废土资料；两者可并用但要标明主次 |
| 女频情感 | 关系结构用 `library-topic-romance-female`<br>虐点反转用 `topic-gouxue-nvwen` | — | 前者管关系线，后者管情绪装置 |
| 短篇 / 短剧 | 知乎体反转用 `topic-zhihu-short`<br>短剧改编用 `library-topic-short-drama-media` | — | 短剧改编还要叠加 `.harness/skills` 里的短剧规则与 H3 规范 |
| 大纲节奏 | `library-writing-outline-pacing` | 内置 `webnovel-writing-basic`、`webnovel-setting-framework` | 先读内置压缩版，需要展开再读远程 |
| 立项市场 | 选题书名简介用 `library-writing-market-concept` | `webnovel-creative-planning`、`webnovel-analysis-commercial-tools` | 创意发散 → 市场工具 → 数据诊断，按阶段递进 |

---

## 五、和内置包、规则的分工

| 你要解决的事 | 先看 | 再看 |
|:-------------|:-----|:-----|
| 判定稿件哪里不合格、改稿门禁 | `.harness/skills/**/rules/`（human-linguistics / plot-review / rhythm-review）+ `included/deslop/去AI味基础包.md` | — |
| 有判定但缺改写手段（句式、修辞、情绪写法） | `library-polish-*` | `library-writing-action-scenes` |
| 缺题材桥段、流派、避坑点 | 第二节的题材包 | — |
| 缺流程、清单、数据判断 | `library-workflow-*`、`library-writing-market-concept` | `webnovel-analysis-commercial-tools` |

原则：**本地规则管「判」，知识包管「料」。** 写完稿的判定标准仍以 `.harness/skills/**/rules/` 为准，知识包不覆盖规则。

---

## 六、分类与检索（技术说明）

| 包前缀 | 归入分类 |
|:-------|:---------|
| `topic-*`、`library-topic-*` | `common.topic` |
| `library-design-*` | `common.setting` |
| `library-writing-*`、`webnovel-*` | `common.writing` |
| `library-polish-*` | `common.humanization` |
| `library-workflow-*` | `common.workflow` |

- 登记位置：`rag/src/normalizer.py` 的 `REMOTE_PACK_CATEGORY`。**新增远程包只需加一行前缀**，否则会落到默认的 `common.topic`。
- 已挂任务路由：`ideation` / `outline_review` / `chapter_prewrite` / `humanization` / `consistency_check` / `rhythm_review` / `genre_routing`（见 `rag/config/task-routes.json`）。
- 索引范围：`.harness/knowledge/remote/**/*.md` 与 `**/*.txt`（部分包的专家提示词是 .txt，已纳入）；`pack.json` 不入索引。
- 分类定义见 `rag/config/categories.json`。

---

## 七、维护命令与版权边界

```powershell
# 看本地已装 / 云端可装
python rag/scripts/sync_packs.py installed
python rag/scripts/sync_packs.py list --include-remote

# 安装 / 更新 / 移除（单包）
python rag/scripts/sync_packs.py install <pack_id>
python rag/scripts/sync_packs.py update <pack_id>
python rag/scripts/sync_packs.py remove <pack_id>

# 装完统一重建索引
python rag/scripts/sync_packs.py rebuild-index
```

版权边界：包内只放自写规则、拆解总结与短句级示例。**不要把包里的内容当原文素材搬运进正文**；需要引用桥段时按本项目「改写不搬运」的原则处理。

换机器 / `remote/` 丢失后，先按本文第二节清单把需要的包重装一遍，再执行一次 `rebuild-index`。

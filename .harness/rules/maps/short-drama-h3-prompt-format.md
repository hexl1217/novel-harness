# 短剧 H3 视频提示词格式

> 用途：短剧编剧 Agent 输出「可直接喂 MiniMax H3」的视频提示词时使用。
> 来源：`MiniMax-H3-Skills-Local/h3-prompt-writing` skill（权威原文）。英文逐字规范见 `.harness/skills/h3-prompt-writing/references/base-en.txt`（T2VA/I2VA/FL2VA/L2VA）与 `ref-en.txt`（Ref2VA）。
> 定位：H3 原生格式的完整写作 Map，规则冲突时以 `references/` 权威原文为准。
> 默认输出：短剧系统中文适配版（见第十一节）；需要逐字对齐 H3 官方原生格式时切「英文原生模式」。

---

## 一、模式判定（先定模式，再写提示词）

| 输入 | 模式 | 何时用 |
|:-----|:-----|:-------|
| 只有文本 | T2VA | 无参考图，从文字直接构建完整音视频时间线 |
| 一张首帧图 | I2VA | 从首帧图向前发展（短剧「关键帧→图生视频」最常用） |
| 首帧 + 末帧两张图 | FL2VA | 描述首帧→末帧连续路径，一般一镜到底，末帧由末镜到达 |
| 一张末帧图 | L2VA | 推断合理前序，收敛到末帧 |
| 图 + 视频 + 音频混合 | Ref2VA | 全参考，六段式改写（见第七节） |

短剧分镜默认场景：**单镜出片 = I2VA**（每镜 1 张关键帧 → 图生视频）；整段连续出片 = T2VA / 多镜 I2VA；需复用音轨 / 人物参考 / 分镜锚点 = Ref2VA。

## 二、基础模式最终结构（T2VA / I2VA / FL2VA / L2VA）

**第一部分 = 指令（图片对齐声明）**，须为第一行，后空一行（T2VA 无指令行）：

- I2VA 固定写法（照抄）：`For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
- FL2VA：`How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.`
- L2VA：`How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.`（N=实际末镜序号，S.SS=有效时长精确两位小数）

**第二部分 = 三个核心字段（顺序固定）**：

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

字段边界（skill 铁律）：

- `integrated_multimodal_description`：全片视觉/动作/镜头/说话人/对白/演唱/画内声的时间线主体。`[Shot 1]` 开头先定整体风格与初始构图（Cinematic / live-action / 2D-animated / 3D CG / claymation / watercolor / vintage film；关键帧任务从参考图取风格）。
- `overall_soundscape`：全片环境声 + 动作声 + 非语言人声的 1–4 句连续段落（风/雨/车流/脚步/布料/撞击/呼吸等）。对白 / 演唱 / 画内音乐**不在此重复**；只有用户明确要求全程静音才写 `N/A`。
- `non_diegetic_music`：只有观众能听到、角色听不到的配乐，1–3 句。写配器、速度、节奏、力度变化，**不写抽象情绪词、不解释配乐情绪功能**。角色能听到的音乐（收音机/电视/电话/人唱歌）属画内事件 → 写进 multimodal，不写这里。无配乐写 `N/A`。

## 三、镜头与剪辑语法

- 首镜不加时间戳：`[Shot 1] Live-action, cinematic, a medium-wide shot frames...`
- 后续镜头用递增切点，切点落在视频时长内：`[Shot 2] At 00:03.500, the camera cuts to...`
- 切镜动词：`the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to`；仅用户明确要求才用 cross-dissolve / fade / wipe。
- 切镜必须带来新信息（主体/空间/状态/视角/时间）；只改距离或微角度 → 用镜头运动，不要切镜。

## 四、镜头运动（类型 + 幅度 + 速度）

- Motion type：Zoom In/Out（变焦）· Push In/Out（推拉）· Pan Left/Right（摇）· Truck Left/Right（横移）· Tilt Up/Down（俯仰）· Pedestal Up/Down（升降）· Arc Shot（环绕）· Tracking Shot（跟拍）· Static Shot（固定）· Shake Slightly/Strongly（微晃/强晃）· POV（主观）· Roll Clockwise/Counterclockwise（滚转）
- Amplitude：`with small amplitude` / `with large amplitude`
- Speed：`at slow speed` / `at fast speed`（中幅度 / 常规速度省略）

写法是镜头内的自然动作句，不堆标签：

```text
The camera pushes in with small amplitude at slow speed toward the folded letter in her hands.
The camera pans right with large amplitude at fast speed, revealing the open doorway.
The camera holds a static shot as the runner exits the frame.
```

## 五、说话人与对白（铁律）

- 会说话 / 唱歌 / 出画外音的角色用稳定 ID `(S1)` `(S2)`；多人齐声用复合 ID `(S1,S2)`；从不出声的角色无 ID。ID 跨镜不变。
- 说话人首现时给出稳定身份信息：角色类型 / 年龄 / 性别 / 是否出画 / 音色 / 语速 / 口音。
- **对白必须用 `<d>[语言] 原词</d>`（铁律）**：说话人身份、ID、动作、语态写在 `<d>` 外；`<d>` 内只放语言标签 + 逐字保留的原文，**不翻译、不改写、不加英文对照**：
  `<d>[Chinese] 把门锁死。</d>`
- 画外音：用 `says in an off-screen voiceover`，其 `<d>` 后补 `while his lips remain completely closed.`（画面中人嘴唇必须闭合）。
- 同句对白跨切镜：两端连接点加 `<scenetrans>`，并写明音频跨切继续；被片尾截断加 `<cutoff>`。连续性用语：`continues seamlessly across the cut` / `carries over from the previous shot` 等。
- 复用音轨（Ref2VA `fully_copy`）：音频是唯一声源——只写谁在何时说、口型跟随音频；**禁止加语气 / 停顿 / 情绪指令**（如 "voice trails off"），否则触发重合成导致语音糊掉。

## 六、画面文字

- 画面可见文字（招牌 / 字幕 / 标签 / 霓虹）用英文双引号，逐字保留不翻译：
  `A red neon sign reading "营业中" glows above the doorway.`

## 七、Ref2VA 六段式（全参考模式）

顺序固定：`subject_definitions` → `summary` → `retention_analysis` → `detailed_description` → `overall_soundscape` → `non_diegetic_music`

### 7.1 参考标签四类（同一标签跨段意义一致）

| 标签 | 含义 |
|:-----|:-----|
| `<Subject N>` | 可复用可见内容（人/景/服装/道具/风格/动作/表情），是真正会被用在目标视频里的内容单元 |
| `<Picture N>` | 参考图（首帧 / 关键帧 / 末帧 / 构图锚点 / 分镜规划） |
| `<Video N>` | 参考视频（编辑源 / 续写起点 / 整片时间结构） |
| `<Audio N>` | 音频（复制 / 音色参考 / BGM 风格 / 对白歌词 / SFX） |

### 7.2 subject_definitions

逐项一行定义标签 + 参考角色 + 主要特征；多源合并写：

```text
<Subject 1> is the woman whose appearance comes from <Picture 1> and whose walking motion comes from <Video 1>.
```

仅当某图/视频只是另一条目的来源、不单独分析时才在其条目内引用，不单列。音频绑定目标说话人时复用其全局 ID：`<Audio 1> is the voice-timbre reference for <Subject 1> (S1).`

### 7.3 summary

一小段英文，以方括号任务类型前缀开头，可组合不重复：

| 任务类型 | 何时用 |
|:---------|:-------|
| `keyframe completion` | 图作首帧 / 关键帧 / 末帧 / 帧锚点 |
| `reference generation` | 图 / 视频 / 音频作生成参考（角色/场景/风格/运镜/分镜），不作具体帧或编辑/续写源 |
| `video editing` | 直接编辑现有源视频 |
| `video continuation` | 从现有源视频续写 / 延伸 / 过渡 |
| `audio reuse` | 原样复用音频信号（全段或部分） |
| `audio reference` | 只参考音频特征（风格/音色/对白歌词/SFX 质感/节奏），不直接复制信号 |

例：`[video continuation + keyframe completion]`；编辑保留原音：`[video editing + audio reuse]`。仅提供运镜/节奏的视频通常属 `reference generation`，不要滥用 editing / continuation。

### 7.4 retention_analysis

每个参考标签一行，用固定标记（固定英文值）：

| 对象 | 标记 |
|:-----|:-----|
| 可见内容 `<Subject>/<Picture>/<Video>` | `fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference` |
| 音频 `<Audio>` | `fully_copy` / `partially_copy` / `reference` / `weak_reference` |

写法：

```text
<Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - ...
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track.
```

只按 subject_definitions 中已定义的参考角色选择标记；目标视频新增的动作/背景/情节不算参考保真度损失。

### 7.5 detailed_description

正文，按播放顺序逐镜描述：构图、主体外貌与位置、环境与光线、动作与状态变化、镜头运动、当前声音、参考内容实际出现/生效的位置。参考标签首次出现时描述其可见特征，之后只复用不重定义。

- 段首用 1–2 句英文定整体风格（放在 `[Shot 1]` 前）。
- 生成类任务通常 350–500 英文词；对白密集时优先铺满完整对白时间线，不机械凑字数。
- 参考标签自然嵌句：`the shot begins from <Picture 1>` / `the shot ends on <Picture 3>`。

### 7.6 音频对齐铁律（Ref2VA 带对白音频时）

1. **先转写再定时间戳**：用 Whisper（faster-whisper，small）拿每句起止时间与说话人 ID，同说话人连续句合并为「回合」，回合间隙即自然切点；`[Shot N] At MM:SS.mmm` 锚定到回合边界，不靠猜。Whisper 可能听错数字/人名，时间戳可信，内容用原稿。
2. **粗对齐不锁帧**：切点大致对齐说话人切换（±0.5–1s 可）；不要在句内停顿处乱切，也不要全删时间戳放任自由生成，两者都会毁节奏。
3. **说话人不匹配 = 硬错**：绝不允许「画面 A 在说话、音频实际是 B 在说」的镜头。逐镜核对时间范围与真实发声说话人一致。

## 八、输出规则

- 默认中文适配（见第十一节）；对齐 H3 官方原生格式时用英文。对白 / 歌词 / 画面可见文字**永远保留原语言**。
- 每镜按「构图 + 主体 + 环境 + 动作 + 镜头 + 声音 + 参考内容出现点」描述。
- 不写剧情梗概；不留未解析参考标签；时间戳必须落在请求时长内。

## 九、声音字段常见错误（对照表）

| 错误 | 正确 |
|:-----|:-----|
| overall_soundscape 里重复对白 / 歌词 | 对白只出现在 multimodal / detailed_description 的 `<d>` 里 |
| non_diegetic_music 写抽象情绪词（"紧张感渐强"） | 写配器 + 速度 + 节奏 + 力度（"低频弦乐持续、速度渐快、音量渐强"） |
| 把角色能听到的音乐写进 music | 画内音乐属 diegetic → 写进 multimodal |
| 每镜都写 `[Shot N] 00:00.000` | 首镜无时间戳；后续镜 `[Shot N] At MM:SS.mmm` 递增 |
| 说话人每镜换 ID | ID 跨镜稳定，首现给身份 |

## 十、生成前自检（H3 专项）

- [ ] **规范先读（硬门禁）**：已读 `.harness/skills/h3-prompt-writing/SKILL.md` + 对应 `references/`（基础模式 base-en.txt / Ref2VA ref-en.txt），未读不得动笔
- [ ] 模式判定正确（单镜关键帧→I2VA；双帧→FL2VA；末帧→L2VA；多参考→Ref2VA）
- [ ] 指令行（I2VA/FL2VA/L2VA）为第一行且后空一行
- [ ] 首镜无时间戳，后续镜时间戳递增且在时长内
- [ ] 对白在 `<d>[语言] 原词</d>` 内、逐字保留；说话人 ID 稳定
- [ ] 画面文字用英文双引号
- [ ] overall_soundscape 无对白；non_diegetic_music 无抽象情绪词
- [ ] Ref2VA：六段齐全、标签跨段一致、retention 标记正确、无未解析标签
- [ ] 音频：先转写后定时间戳，无说话人不匹配

## 十一、中文适配说明（短剧系统默认）

短剧编剧 Agent 默认输出**全中文 H3 三字段**（MiniMax H3 对中文自然语言支持好，且便于与分镜脚本对齐）。中文适配规则：

- 字段名保持英文：`integrated_multimodal_description:` / `overall_soundscape:` / `non_diegetic_music:`。
- 对白、画面文字、人名、招牌保留原文并加「」或引号；说话人 ID `(S1)/(S2)`、`<d>`、`<scenetrans>`、`<cutoff>` 标签保留英文（中文对白放 `<d>[Chinese] …</d>`）。
- 时间码 `[Shot N]` / `At MM:SS.mmm` 保持英文语法；其余描述用中文自然语言。
- 镜头运动按「类型 + 幅度 + 速度」翻译为中文动作句（"镜头以小幅度缓慢推近她的手指"），不堆标签。
- 需要逐字对齐 H3 官方原生格式时切「英文原生模式」，按 base-en.txt / ref-en.txt 输出英文（对白 / 画面文字仍保留原语言）。

## 十二、示例

### 示例 A：中文适配版 · I2VA（单镜，10s 悬疑出片）

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] 实拍电影感，夜晚，低照度冷调，镜头固定。26岁瘦削中国女性齐肩碎发、穿深灰针织开衫内搭白T恤，握切肉菜刀站在木质吧台后，神情紧张克制，警觉望向阴影中的楼梯口，楼梯口阴影浓重。真人写实，画面清晰锐利，结构比例正常，无多余肢体与手部畸形，无水印文字。同步室内几乎静默、远处楼道传来极轻的摩擦声与她的呼吸声。
overall_soundscape: 室内几乎静默，远处楼道传来极轻的摩擦声，呼吸声清晰，心跳声渐起。
non_diegetic_music: 低频悬疑弦乐持续，速度渐快，音量渐强。
```

### 示例 B：中文适配版 · 多镜 I2VA（连续出片）

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] 实拍电影感，中景，中焦距，暖钨丝灯实用光，暖琥珀色调，镜头横移跟随。26岁瘦削中国女性齐肩碎发绕过木质吧台走到窗边，伸手缓缓拉开窗帘，侧影轮廓清晰，室内暖光与窗外冷调并置。真人写实，画面清晰锐利，结构比例正常，无多余肢体与手部畸形，无水印文字。同步脚步声与窗帘滑轨声，环境底噪渐静。 [Shot 2] At 00:05.000，镜头切至全景，对称构图，广角焦段，路灯灯光穿过浓雾作背光，冷灰调。窗外浓雾剧烈翻涌，像有人从天上倒面粉，路灯晕成光团，街对面六层楼只剩剪影，雾气缓慢向画面方向蔓延。同步低沉雾涌嗡鸣声渐起，环境底噪几乎消失。
overall_soundscape: 脚步轻响，窗帘滑轨摩擦声，窗外风声渐起，随后转为低沉的雾涌嗡鸣，底噪几乎消失。
non_diegetic_music: 低频持续音铺底，节奏极缓，制造不安感。
```

### 示例 C：Ref2VA 六段式（英文原生）

英文原生模式按 `.harness/skills/h3-prompt-writing/references/ref-en.txt` 第七节完整示例输出（subject_definitions → summary → retention_analysis → detailed_description → overall_soundscape → non_diegetic_music），说话人用 `(S1)/(S2)`、对白用 `<d>[语言] …</d>`、参考标签跨段一致、retention 用固定标记。

---

## 附：文件导航

- 权威原文（英文，逐字规范）：`.harness/skills/h3-prompt-writing/references/base-en.txt`、`ref-en.txt`；skill 入口：`.harness/skills/h3-prompt-writing/SKILL.md`
- **读取顺序（硬门禁）**：`SKILL.md`（判模式）→ `references/base-en.txt`（T2VA/I2VA/FL2VA/L2VA）或 `references/ref-en.txt`（Ref2VA 六段式、带音频）→ 本 Map 中文适配。未读权威原文不得直接写 H3 提示词。
- 本 Map 是给短剧编剧 Agent 的中文落地版；不确定处回权威原文查证。

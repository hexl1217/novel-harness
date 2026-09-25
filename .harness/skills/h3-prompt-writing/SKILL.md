---
name: h3-prompt-writing
description: 为 T2VA、I2VA、FL2VA、L2VA 与 Ref2VA 编写 MiniMax H3 视频生成提示词。用于把多模态请求改写为 H3 提示词结构、撰写 integrated_multimodal_description / overall_soundscape / non_diegetic_music、对齐关键帧，或为图片、视频、音频定义参考标签。
compatibility: 可移植到任何能读取本地文件的 Agent——无需外部 API 调用、MiniMax Hub 工具或专有运行时。agents/openai.yaml 文件仅添加可选的 ChatGPT/Codex UI 元数据，并不把本 skill 限制在 OpenAI Agent 上。
---

# H3 提示词写作

> 本文件是 `MiniMax-H3-Skills-Local/h3-prompt-writing` 的本地权威副本，供 novel-harness 短剧编剧 Agent 在写 H3 提示词时对照权威原文。
> 中文落地规则见 `.harness/rules/maps/short-drama-h3-prompt-format.md`；本 skill 是英文权威规范，规则冲突时以本文件 + references/ 原文为准。

## 工作流程

1. 识别输入模式：T2VA、I2VA、FL2VA、L2VA 或全参考 Ref2VA。
2. 基础文本/关键帧模式下，读取 `references/base-en.txt` 并遵循其最终提示词结构。
3. 全参考模式下，读取 `references/ref-en.txt` 并遵循其六段式改写格式。
4. 严格保留所选指南中的字段名、段落顺序、标签与时间码写法。

## 基础模式

- T2VA：从文本构建完整的音视频时间线。
- I2VA：从首帧出发，向前发展。
- FL2VA：描述首帧与末帧之间的连续路径。
- L2VA：推断合理的开头，收敛到所提供的末帧。

按 `references/base-en.txt` 所示的顺序使用 `integrated_multimodal_description`、`overall_soundscape` 与 `non_diegetic_music`。

## 全参考模式

Ref2VA 改写按顺序使用 `subject_definitions`、`summary`、`retention_analysis`、`detailed_description`、`overall_soundscape` 与 `non_diegetic_music`。参考标签在所有段落中保持一致。

读取 `references/ref-en.txt` 了解标签规则、保留度分析与完整示例。

## 音频时间线对齐（带对白音频的 Ref2VA）

当输入包含对白/语音音频（`<Audio N>`）时，**先转写音频，再设定镜头时间戳**——这是带音频 Ref2VA 中最常见的失败点：说话人不匹配（画面中 A 角色正在说话，而音频已经切到 B 角色）。

- **音频优先：** 运行 Whisper（`faster-whisper`，模型 `small`）获取每句话的起止时间戳与说话人 ID（可区分时用 S1/S2）。把同一说话人的连续语句合并为「回合」；回合之间的间隙就是自然的切点。把每个 `[Shot N] At MM:SS.mmm` 锚定到这些回合边界——不要盲目猜测。注意：Whisper 可能听错数字/人名（例如「心之星」→「星之星」）；时间戳可信，内容使用用户原文。
- **粗对齐而非锁帧：** 镜头切点应大致对齐音频中的说话人切换边界（±0.5–1s 即可），但不要帧级精确绑定。在句内每个停顿处都切，或删除所有时间戳让模型自由发挥，两者都会让节奏变差。
- **硬性规则——不允许说话人不匹配：** 绝不让「画面中 A 角色正在说话」的镜头，重叠到「音频实际是 B 角色在说话」的片段上。逐镜核对每个 `[Shot N]` 的时间范围与该范围内真正发声的说话人（S1/S2）一致。

## 输出规则

- **对白/歌词必须使用 `<d>[语言] ... </d>` 标签（铁律）。** 说话人的身份说明、ID、动作与语态写在 `<d>` 之外；`<d>` 内只放语言标签与逐字保留的原文——保留每一个原词与标点，不翻译、不改写、不追加英文对照。示例：`<d>[Chinese] 今天的星星，好像比昨天暗了一点点。</d>`、`<d>[English] I get off at the next station.</d>`。脚本块与每个镜头描述都必须遵守这一条。
- **音频复用模式（fully_copy）：绝不重新合成。** 当 `<Audio N>` 被原样复用为最终音轨时，音频是唯一声源——只描述谁在何时说话、口型跟随音频。不要添加语气/韵律/停顿/情绪指令（例如「voice trails off」「scholarly tone」），这会触发重新合成并导致语音糊掉。
- 改写段落用英文书写；对白、歌词与画面可见文字保留原文。
- 按构图、主体、环境、动作、镜头、声音，以及参考内容出现的精确位置，逐镜描述。
- 避免剧情梗概、未解析的参考标签，以及与请求时长不匹配的时间码。

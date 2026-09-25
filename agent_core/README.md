# agent_core

`.harness` 是给 LLM 读的规则层（Markdown 提示词）；`agent_core` 是**能被机器执行**的那部分规则。

分界原则：

- 需要判断语义、人设、节奏的 → 留在 Markdown，交给 LLM。
- 字面稳定、误伤可控、有明确阈值的 → 放进这里，用代码判，不再靠 LLM 自我申报。

## 模块

| 文件 | 状态 | 说明 |
|:-----|:-----|:-----|
| `check_draft.py` | 可用 | 正文机器预检：把规则里可判定的条款落成确定性校验 |
| `state.py` | 可用 | 运行时状态落盘：挂起恢复栈、开书阶段 S0–S5、已锁定题材/平台/知识包 |
| `state_machine.py` | 原型 | 单章流水线状态机（准备–写作–审稿–归档） |
| `engine.py` | 原型 | 引擎外壳，负责串联状态机与落盘 |
| `project.py` | 原型 | 项目存储，路径对齐 `projects/{项目}/正文/第N章.md` |
| `test/` | — | 单元测试，`python -m pytest agent_core/test/` |

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

CI 已经跑起来了（`.github/workflows/ci.yml` 的 `check-draft` job）；审稿清单的「表零」与交付清单的「机器预检」行都以它为准。

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

改检查项时同步改 `test/test_check_draft.py`。规则文件是唯一真源——如果规则变了，这里要跟着变，而不是反过来。

提交前本地过一遍 CI 的同等检查：

```bash
python -m pytest agent_core/test/
python -m pyflakes agent_core/
python -m pycodestyle agent_core/ --max-line-length=120 --ignore=E402,W503
python -m agent_core.check_draft projects --allow-empty
```

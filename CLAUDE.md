# novel-harness Claude 入口

@AGENTS.md

## Claude Code 专用说明

上面那一行 `@AGENTS.md` 是 Claude Code 的**导入语法**，会把 `AGENTS.md` 完整加载进会话。本文件**故意只做导入，不复制任何规则**。

为什么不在 `CLAUDE.md` 里再写一份：

- 此前 `AGENTS.md`、`CLAUDE.md`、`skills/novel-core/SKILL.md` 三份各自抄了一遍触发词和默认流程，实测重复度 40%–67%。改一条规则要同步三处，`CLAUDE.md` 和 `AGENTS.md` 已经开始分叉。
- **要改规则，改 `AGENTS.md`。**`CLAUDE.md` 和 `SKILL.md` 都会跟着走。

关于导入语法的两点事实（来自 Claude Code 官方文档）：

- Claude Code 读 `CLAUDE.md`，不读 `AGENTS.md`，所以导入是两边共用同一份指令的正规做法。
- 符号链接（`ln -s AGENTS.md CLAUDE.md`）在 Windows 上需要管理员权限或开发者模式，而且 Git 检出时会把符号链接退化成纯文本文件——所以这里用 `@AGENTS.md` 导入，不用符号链接。
- 验证：下次会话执行 `/context`，确认 `CLAUDE.md` 出现在 Memory files 下。若没有，说明导入未生效。

## 仓库自带的可执行工具

不依赖 MCP，直接跑：

```bash
python -m agent_core.check_draft projects/{项目}/正文/第{N}章.md   # 正文机器预检
python -m agent_core.state show                                    # 运行时状态与挂起恢复栈
```

单章默认加载集合见 `.harness/rules/maps/chapter-required-reading.md`。

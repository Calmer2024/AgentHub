# 02 — 问题清单

## P1. 输出语言继承缺失

中文需求下，部分 Agent 产物变成英文：

- `home-assets-demo/README.md`
- `home-assets-demo/HANDOFF.md`
- T2/T3/T4 `HANDOFF.md`
- 前端 UI 文案
- 前端错误提示
- 后端错误信息

示例：

```text
Home Assets Manager
Add New Asset
Asset List
Failed to load assets
Delete "{name}"? This cannot be undone.
```

根因判断：

- 真实任务 prompt 强调“聊天简短、文件写工作包”，但没有强约束“继承用户语言”。
- 完整计划 JSON 是中文，但 CLI Agent 容易回到英文工程默认风格。

建议：

- 在 `CliTaskRunner._task_prompt()` 中加入语言约束。
- Orchestrator plan 可显式写入 `language: "zh-CN"` 或 `output_language`。
- `TASK.md` 同步写入语言约束。
- 技术标识符、API path、变量名、包名保持英文即可。

## P2. Agent 气泡仍然过长

实际 T2/T4 气泡包含大量过程性文字：

- 我会先读取...
- 接下来会...
- 准备写入...
- 我现在跑安装/构建...

问题：

- 主聊天消息流阅读成本高。
- 用户难以快速判断任务是否完成。
- 过程性信息应进入 trace，而不是主气泡。

建议：

- Agent 最终气泡只保留最终摘要。
- 中间过程进入 `executionTrace`。
- 后端可在持久化前做最终摘要提取，避免把全部 streaming text 都作为 visible content。

## P3. Trace 缺少状态分层

T2/T4 trace 中有错误项，但最终成功。

T2 失败尝试：

- Python stdin 被 BOM `U+FEFF` 绊倒。
- `TestClient` 依赖异常：`No module named 'httpx2'`。
- 非 git 目录执行 `git status --short` 失败。

T4 失败尝试：

- 默认 `8000` 被 AgentHub 后端占用，访问 `/health` 返回 AgentHub 的 404。
- 一次 PowerShell `Invoke-WebRequest` 删除验证脚本报空引用。
- 非 git 目录执行 `git diff/git status` 失败。

问题：

- UI 看到 error trace 会以为任务失败。
- 实际这些是中途探索失败，最终 Agent 绕过去并完成验证。

建议：

- trace metadata 增加 `recoveredErrors`、`blockingErrors`、`expectedFailures`。
- 前端显示“最终成功，含恢复项”。
- 测试 Agent 最终报告说明失败原因、替代验证方式、最终结果。

## P4. 消息 API 返回过重

`GET /api/sessions/{id}/messages` 当前会带完整 `executionTrace`。本次 T4 单条消息有 219 条 trace item。

建议：

- 消息列表只返回 trace 摘要。
- 新增懒加载接口：

```text
GET /api/messages/{message_id}/trace
```

或：

```text
GET /api/sessions/{session_id}/messages/{message_id}/trace
```

## P5. 文件变化噪音大

真实执行会产生：

- `node_modules/`
- `package-lock.json`
- `assets.db`
- `__pycache__/`
- build/dist 产物

建议：

- 文件树、diff、Artifact Bridge 默认过滤运行噪音。
- 可提供“显示全部生成文件”开关。
- lock 文件可折叠显示。

## P6. 验收报告没有完整解释失败尝试

T4 最终报告写了 port 8000 被占用，但没有完整列出：

- 哪些验证命令失败
- 失败是否影响最终结果
- 后续如何替代验证

建议：

- 测试 Agent prompt 增加验收报告模板：
  - 通过项
  - 失败后恢复项
  - 未验证项
  - 残余风险
  - 最终结论

## P7. 前端本地化问题

前端固定：

```ts
new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
```

中文家庭资产场景应更适合：

```ts
new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' })
```

建议：

- 语言继承 prompt 要求 locale/currency 跟随用户语言。
- 生成项目可用简单常量集中定义 locale/currency。

## P8. UI 体验偏基础

生成 demo 可以运行，但体验仍偏 MVP：

- 删除使用 `window.confirm`。
- 表单提示和错误处理较粗。
- 页面文案未本地化。
- 没有更细的 loading/disabled/error 状态。

这不是 Orchestrator 阻塞问题，但后续如果要验证“高质量落地”，需要在任务提示或 Agent profile 中提升 UI 验收标准。

## P9. Agent 对运行目录边界仍会误撞

多次看到 Agent 在非 git 目录跑：

```text
git status --short
git diff ...
```

并失败：

```text
fatal: not a git repository
```

建议：

- 任务 prompt 明确当前 cwd 是任务工作包，不一定是 git 仓库。
- 需要 git 前先判断 `.git` 是否存在。
- trace UI 把这种环境探测失败标记为 non-blocking。

## P10. 中断/取消需要专项验收

当前后端已有 `cancel_execution()` 和 CLI session terminate 逻辑，但真实长任务场景还没有完整验收。

需要覆盖：

- 用户点击停止后 execution 状态从 `running/cancelling` 到 `cancelled`。
- 正在运行任务变 `cancelled`。
- pending 任务不再启动。
- CLI 进程确实终止。
- Agent 气泡持久化为取消状态。
- 前端状态面板不再自动轮询到 completed。
- 刷新后消息和 execution 状态一致。


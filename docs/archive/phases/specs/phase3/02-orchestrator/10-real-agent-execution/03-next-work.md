# 03 — 后续工作

## 合并队友代码前

建议先提交当前本地 Orchestrator 真实执行阶段的已完成修改，避免和队友功能混在一个提交里。

合并前记录：

```bash
git status --short
git log --oneline -5
git diff --stat
```

当前需要额外确认的未跟踪文件：

```text
HANDOFF.md
tmp.json
```

`tmp.json` 是调试样本，不建议误提交。`HANDOFF.md` 已覆盖为当前阶段中文交接。

## 拉取与合并队友功能

建议顺序：

1. 提交当前小阶段。
2. `git fetch` / `git pull` 获取队友代码。
3. 先看冲突文件是否集中在：
   - `backend/app/services/orchestrator_execution.py`
   - `backend/app/api/orchestrator.py`
   - `frontend/src/components/MessageBubble.tsx`
   - `frontend/src/components/ExecutionTracePanel.tsx`
   - `frontend/src/components/OrchestratorExecutionPanel.tsx`
   - `frontend/src/api/client.ts`
4. 合并后先跑单元/构建，再跑真实 Orchestrator smoke。

## 合并后第一轮回归

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest test_api/test_orchestrator_execution.py -q
.\.venv\Scripts\python.exe -m pytest test_api/test_group_chat.py -q
```

前端：

```powershell
cd frontend
npm run build
```

真实手工 smoke：

1. 新建或选择一个临时 Project workspace。
2. 创建群聊，包含 Orchestrator 和至少 4 个角色 Agent。
3. 输入中文需求，要求生成 4 步串行计划。
4. 批准执行。
5. 观察：
   - execution panel 从 pending/running 到 completed。
   - 每个任务出现真实 Agent 气泡。
   - Agent 气泡有 trace 面板。
   - 工作包目录存在。
   - 生成项目能启动或至少通过 T4 验收。
6. 刷新页面后确认 Agent 消息和 trace 仍存在。

## 推荐开发切片

### Slice A: 语言继承

目标：

- 中文需求下，Agent 输出、README、HANDOFF、前端 UI 文案默认中文。

修改点：

- `CliTaskRunner._task_prompt()`
- Orchestrator plan prompt 或 plan normalization 增加语言字段
- `TASK.md` 写入语言约束

验收：

- 用中文提示词生成并执行小项目。
- T2/T3/T4 交接文档为中文。
- 前端 UI 文案为中文。
- API path、变量名、包名可保持英文。

### Slice B: Agent 气泡瘦身

目标：

- 主聊天只显示最终 5 行左右摘要。
- 中间过程进入 trace。

修改点：

- `CliTaskRunner.run()` 中 `visible` 内容聚合策略
- 或增加最终摘要提取函数

验收：

- T2/T4 不再把长过程输出塞进气泡。
- trace 面板仍能看到详细过程。

### Slice C: Trace 状态分层

目标：

- 区分最终成功、中途失败后恢复、真正失败。

修改点：

- `ExecutionTraceBuilder`
- trace metadata schema
- `ExecutionTracePanel`

验收：

- T2/T4 这种中途失败但最终成功的任务显示为“已完成，含恢复项”。
- 真正 exit code 非 0 的任务显示为失败。

### Slice D: Trace 懒加载

目标：

- 消息列表不返回完整 trace。
- 点击执行过程时再取完整 trace。

修改点：

- message read schema
- 新 trace API
- 前端 trace panel fetch

验收：

- `/api/sessions/{id}/messages` 响应显著变小。
- 刷新后仍可展开完整 trace。

### Slice E: 文件变化过滤

目标：

- 产物/文件变化视图默认过滤运行噪音。

修改点：

- `LocalWorkspaceProvider`
- `FileChangeDetector`
- Artifact Bridge 规则

验收：

- `node_modules`、`__pycache__`、`.db` 不作为主要产物刷屏。
- 用户仍可选择显示全部。

### Slice F: 取消/中断真实验收

目标：

- 用户能在真实长任务中停止执行。

修改点：

- 已有 `cancel_execution()` 基础上补 UI 和测试。
- CLI process terminate 后消息状态处理。

验收：

- 运行中点击停止。
- CLI 进程被终止。
- running task 变 cancelled。
- pending task 不启动。
- 刷新后一致。

## 风险与注意事项

1. 真实 CLI Agent 会消耗 token 和时间，合并后回归要用极小任务。
2. 并行任务容易造成文件冲突，短期建议默认串行验证。
3. 当前 execution registry 是内存态，服务重启后 `GET /api/orchestrator/executions/{id}` 可能 404；消息记录仍在数据库。
4. 如果要支持中断恢复，需要持久化 execution state，而不是只从内存 registry 读。
5. Demo 项目中的 `assets.db` 是业务库，不要误认为 AgentHub 消息库。
6. PowerShell + Python stdin 容易出现 BOM 问题，真实 Agent 验证脚本应尽量用 `python -c` 或写临时脚本文件。
7. 端口 `8000` 经常被 AgentHub 自己占用，生成项目验收应允许改端口并同步前端 proxy。


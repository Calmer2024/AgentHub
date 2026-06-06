# AgentHub 交接 — Orchestrator 真实 Agent 执行阶段

**日期**: 2026-06-06  
**当前工作区**: `D:\08Projects\2026\AgentHub`  
**下一步**: 拉取并合并队友功能，然后围绕真实执行体验做回归和打磨。

---

## 当前状态

Orchestrator 已从“生成计划 + 模拟 DAG”推进到“用户批准 draft plan 后调度真实 CLI Agent 执行”。

已阶段性验证：

- 调度器生成 draft plan。
- 用户说“可以执行”后创建 execution。
- Scheduler 按 DAG 拓扑推进任务。
- 真实 CLI Agent 被调起。
- Agent 气泡进入群聊消息流。
- 任务结果与 `executionTrace` 落库。
- 每个任务有独立工作包。
- 下游 Agent 能读取上游交接继续执行。
- 最终可以在 workspace 中生成可运行 demo 项目。

真实验收样本：

```text
session_id: 5fd075e2-36d1-47bf-bc86-477e7aa0fba9
execution_id: exec_f3a779b681e7
workspace: D:\08Projects\example\agenthub\billManager
generated_app: D:\08Projects\example\agenthub\billManager\home-assets-demo
```

详细复盘已拆分到：

```text
docs/specs/phase3/02-orchestrator/10-real-agent-execution/
```

阅读入口：

- `README.md`：结论和阅读顺序
- `01-acceptance-record.md`：验收样本和 trace 统计
- `02-issues.md`：问题清单
- `03-next-work.md`：合并后续计划

---

## 当前主要问题

1. 中文需求下，部分 Agent 交付物、README、前端 UI 文案变成英文。
2. Agent 气泡仍混入太多过程性文字，主聊天不够简洁。
3. trace 里“中途失败后恢复”和“最终失败”没有状态分层。
4. 消息列表 API 携带完整 trace，真实长任务下响应过重。
5. 文件变化/产物视图需要过滤 `node_modules`、`.db`、`__pycache__` 等噪音。
6. 中断/取消真实长任务还需要专项验收。

权威问题清单见：

```text
docs/specs/phase3/02-orchestrator/10-real-agent-execution/02-issues.md
```

---

## 合并队友代码前

建议先提交当前小阶段，避免和队友功能混在一起。

当前未跟踪文件：

```text
HANDOFF.md
docs/specs/phase3/02-orchestrator/10-real-agent-execution/
tmp.json
```

说明：

- `HANDOFF.md` 是当前交接。
- `10-real-agent-execution/` 是本阶段复盘文档。
- `tmp.json` 是早期调试样本，除非明确需要，否则不建议提交。

---

## 合并后优先回归

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

1. 新建或选择临时 Project workspace。
2. 创建群聊，包含 Orchestrator 和至少 4 个角色 Agent。
3. 用中文要求生成 4 步串行计划。
4. 批准执行。
5. 确认 execution panel、Agent 气泡、trace、任务工作包、生成项目都正常。
6. 刷新后确认 Agent 消息和 trace 仍存在。

---

## 下一批建议切片

1. 语言继承：中文需求下，README、HANDOFF、UI 文案默认中文。
2. Agent 气泡瘦身：主聊天只显示最终摘要，中间过程进 trace。
3. Trace 状态分层：区分最终失败、预期失败、失败后恢复。
4. Trace 懒加载：消息列表只带摘要，展开时再取完整 trace。
5. 文件噪音过滤：默认隐藏运行副产物。
6. 取消/中断验收：真实长任务停止后状态、进程、消息落库一致。

详细计划见：

```text
docs/specs/phase3/02-orchestrator/10-real-agent-execution/03-next-work.md
```

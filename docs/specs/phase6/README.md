# Phase 6: CLI 适配器 (Architecture Foundation Fix) 📋 PLANNED

**关联 ADR**: [ADR-0008](../../adr/0008-revised-development-strategy.md) §6
**关联 PRD**: [PRD-01: Architecture Adapter](../../PRD/01-Architecture_Adapter.md)
**依赖**: Phase 3 (BaseAgentAdapter 接口), AgentPanel 配置系统
**状态**: 计划中

---

## 1. 板块目标

实现 PRD-01 定义的 CLI Agent 封装能力。这是 PRD 的核心架构承诺 —— AgentHub 不应只是"调 HTTP API"，而应能管理真实的 CLI Agent 工具（如 `claude` 命令），提供真正的 Agent-as-a-Service。

**关键原则**：
- 作为**新增能力**，不影响现有 HTTP 适配器的正常运行
- 通过 `agent_type: 'cli_wrapper'` 区分，与 `agent_type: 'api_proxy'` 并存
- Orchestrator 无需修改 —— 它通过 `BaseAgentAdapter` 抽象接口工作

---

## 2. 子模块

### Module 6A: CLI Process Manager

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §3 |
| **后端** | `backend/app/infrastructure/cli_process_manager.py` |
| **职责** | PTY/subprocess 进程孵化、CWD 管理、环境变量隔离、心跳超时、SIGTERM/SIGKILL |

### Module 6B: Stream Sanitizer (ANSI 清洗)

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §4 |
| **后端** | `backend/app/infrastructure/stream_sanitizer.py` |
| **职责** | ANSI 转义码正则过滤、分块 SSE 推送 (50ms)、TUI 组件降级渲染 |

### Module 6C: Interactive Prompt Interception

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §5 |
| **后端** | `backend/app/infrastructure/prompt_interceptor.py` |
| **前端** | `InteractivePromptCard.tsx` |
| **职责** | 滑动窗口缓冲区 + 阻塞特征匹配 → 暂停推流 → 前端信令卡片 → stdin 回写 |

### Module 6D: CLI Agent Adapter

| 维度 | 内容 |
|------|------|
| **Spec** | [01-cli-adapter.md](01-cli-adapter.md) §6 |
| **后端** | `backend/app/agents/cli_adapter.py` |
| **职责** | 实现 `BaseAgentAdapter`、整合以上 3 模块、在 AgentPanel 中可选 |

---

## 3. 验收标准

- [ ] **6A-1**: AgentConfig 中 `agent_type='cli_wrapper'` → 启动对应的 CLI 进程（如 `claude`）
- [ ] **6A-2**: 进程 stdout → 实时推流到前端 → 打字机效果流畅（延迟 < 100ms）
- [ ] **6A-3**: 用户关闭网页 → 3 分钟后进程收到 SIGTERM → 进程正常退出
- [ ] **6A-4**: stdout 静默超过 5 分钟 → 判定死锁 → SIGKILL → 前端显示"进程已超时"
- [ ] **6B-1**: ANSI 颜色码 `\x1b[31mError\x1b[0m` → 前端收到 `Error`（无乱码）
- [ ] **6B-2**: 复杂 TUI 输出（进度条、表格）→ 降级为纯文本
- [ ] **6C-1**: Claude Code 输出 `Do you want to run this? (y/n)` → 前端弹出交互卡片
- [ ] **6C-2**: 用户点击 [同意] → stdin 写入 `y\n` → 进程继续执行
- [ ] **6C-3**: 用户点击 [拒绝] → stdin 写入 `n\n` → 进程收到拒绝信号
- [ ] **6D-1**: CliAgentAdapter 在 AgentPanel 中可配置（executable 路径 + init_args + env vars）
- [ ] **6D-2**: CliAgentAdapter 与现有 HTTP 适配器在同一个会话中共存（群聊中混合使用）

---

## 4. 接口契约

### CliAgentAdapter 必须实现

```python
class CliAgentAdapter(BaseAgentAdapter):
    """CLI Agent 适配器 —— 通过 PTY/subprocess 管理真实 CLI 工具。"""
    
    @property
    def capability(self) -> AgentCapability: ...
    
    async def chat(self, messages, system_prompt, on_token=None) -> AgentResponse: ...
    async def chat_stream(self, messages, system_prompt) -> AsyncIterator[str]: ...
```

### 新增 SSE 事件

```json
{"type": "interactive_prompt", "content": "Do you want to run this? (y/n)", "processId": "..."}
```

### 新增 API

```
POST /api/sessions/{id}/interactive_reply
  Body: { "process_id": "...", "reply": "y" }
  → 200 { "status": "acknowledged" }
```

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Windows PTY 支持不如 Unix | 使用 `subprocess.Popen` + 管道作为 Windows fallback |
| CLI 工具版本差异导致解析失败 | 阻塞特征匹配用正则而非硬编码字符串 |
| 长时间进程占用内存 | 心跳超时 5min + 定期清理僵尸进程 |
| CLI 工具不在 PATH 中 | AgentConfig 中配置绝对路径，启动前检测可执行文件存在 |

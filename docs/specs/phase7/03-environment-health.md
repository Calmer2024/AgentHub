# Spec: Phase 7C — 环境体检

**版本**: v2.0
**创建日期**: 2026-06-06
**状态**: 验收通过
**关联 ADR/PRD**: [ADR-0009](../../adr/0009-project-workspace-model.md)、[PRD-01](../../PRD/01-Architecture_Adapter.md)、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[PRD-06](../../PRD/06-MVP_Local_Workspace_Delivery.md)
**依赖模块**: Agent Registry、Project Workspace Runtime、SystemLLMService、Phase 7A Run 状态

> 2026-06-06 实现同步：本模块已落地 `SystemHealthService`、`GET /api/system/health`、`POST /api/system/health/check` 与前端 `HealthCheckCard`/发送前 guard。体检聚合 CLI executable、Codex 本机配置、Node/Python、workspace、DeepSeek 系统模型和活跃 CLI 进程，不返回 API key/token 等敏感值。

---

## 1. 目标

本模块在用户启动复杂任务前，提供统一、可操作、不可泄露密钥的环境体检结果。Phase 6 已能在 Agent 列表中检测单个 executable，并有 DeepSeek 系统模型状态函数，但缺少一个聚合 API 和前端入口来回答：“当前 Project、CLI Agent、Node/Python、系统模型、活跃进程是否支持我马上执行任务？”

目标用户是本机桌面版开发者。体检结果要帮助用户快速判断为什么 Agent 不能执行，而不是把错误留到 CLI 进程启动后才暴露。

**成功标准**（可证伪）：

- [x] `GET /api/system/health?projectId=&sessionId=` 返回统一 health payload，包含 overall、items、blockingReasons。
- [x] 体检聚合 CLI Agent executable 状态、Codex 配置、Node/Python 运行时、workspace 可读写、DeepSeek 系统模型、活跃 CLI 进程。
- [x] 前端左侧或 ChatHeader 显示紧凑 HealthCheckCard；缺失 CLI 或 workspace 不可写时，在创建/发送关键路径阻断或警告。
- [x] 返回 payload 不包含任何 API key、token、用户完整敏感 env 值。
- [x] 不通过标准：只在 AgentPanel 显示 executable 状态，但 Chat 发送路径仍然失败后才报错。

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
Project / Agent / runtime 配置
  → [本模块] SystemHealthService
  → HealthCheckCard + create/send guard
  → CLI Agent 执行
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | Agent Registry executable status | 聚合每个 CLI Agent 可用性 |
| **上游输入** | Project workspace path | 检测目录存在、可读、可写 |
| **上游输入** | SystemLLM `system_model_status()` | 展示标题/总结/编辑辅助能力状态 |
| **上游输入** | Run/Process runtime | 展示活跃进程与异常进程 |
| **下游产出** | `/api/system/health` | 前端 HealthCheckCard、Chat guard、AgentPanel 消费 |
| **本模块不通** | 自动安装或自动登录 CLI | 用户外部处理 |

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/system/health` | GET | query: `projectId?`, `sessionId?` | `200: SystemHealthRead` | 只在服务异常时 500 |
| `/api/system/health/check` | POST | `{ projectId?, sessionId?, agentId? }` | `200: SystemHealthRead` | 只在服务异常时 500 |

`GET` 用于页面加载和轮询；`POST /check` 用于用户点击刷新或发送前强校验。

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `system.health.updated` | 后端 → WS | `{ overall, itemCount, blockingReasons, checkedAt }` |
| `system.health.degraded` | 后端 → WS | `{ key, status, severity, message }` |

MVP 可先不做后台推送，前端在进入 Project、Agent 配置变更、发送前主动请求。

### 3.3 数据库 Schema 变更

本模块不新增持久化表。health 是当前环境快照，不写入数据库。若需要调试，可写日志但不得记录密钥值。

### 3.4 跨组件 TypeScript 类型

```typescript
type HealthStatus = "ok" | "warning" | "error" | "missing";
type HealthSeverity = "info" | "warning" | "blocking";

interface SystemHealthItem {
  key: string;
  label: string;
  status: HealthStatus;
  severity: HealthSeverity;
  detail: string;
  action?: {
    label: string;
    target: "agent_panel" | "project_settings" | "docs" | "retry";
  };
  metadata?: Record<string, string | number | boolean | null>;
}

interface SystemHealthRead {
  overall: "ok" | "warning" | "error";
  checkedAt: string;
  projectId?: string | null;
  sessionId?: string | null;
  blockingReasons: string[];
  items: SystemHealthItem[];
}
```

---

## 4. 行为规格

### 4.1 正常流程

```text
1. 用户进入 Project 工作区
   → 前端 GET /api/system/health?projectId=...
   → HealthCheckCard 显示 overall 状态

2. 用户展开体检卡片
   → 前端显示 CLI、runtime、workspace、system model、process 组
   → 每个异常项提供“去配置/重试/查看项目”操作

3. 用户点击发送消息
   → 前端 POST /api/system/health/check { sessionId, agentId }
   → 如果有 blockingReasons，阻断发送并显示原因
   → 如果只有 warning，允许发送但显示非阻断提示

4. 用户修复配置
   → 点击重试
   → 体检结果更新
```

### 4.2 检测项

| key | 检测方式 | 状态规则 |
|-----|----------|----------|
| `agent.{id}.executable` | 复用 `CliAgentRegistry.executable_status(agent.executable)` | ready→ok；not_found→missing/blocking |
| `agent.codex.config` | 复用 `CodexLocalConfigService.status()` | ready→ok；needs_api_key→warning/blocking 视当前 agent |
| `runtime.node` | `node --version`，timeout 2s | 存在→ok；缺失→warning |
| `runtime.python` | 当前后端解释器或 `python --version` | 存在→ok；异常→error |
| `workspace.path` | Project.workspace_path exists/is_dir/readable/writable | 不存在或不可写→blocking |
| `system.deepseek` | `system_model_status()` | 未配置→warning，不阻断 CLI 对话 |
| `process.active` | `cli_runtime_registry.active_snapshots(sessionId?)` | 有进程→info；异常残留→warning；同时覆盖短进程、Claude Code 会话级常驻 stdin JSONL 进程和 Codex/OpenCode 会话级常驻 RPC 进程 |

### 4.3 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | “未选择项目，无法体检 workspace” | 无 project/session |
| **加载态** | 小型 skeleton 或 Loader2 | 请求中 |
| **正常态** | 绿色状态点 + “环境就绪” | overall=ok |
| **完成态** | 点击刷新后显示“刚刚检查” | POST check 成功 |
| **错误态** | 琥珀/红色状态点 + blockingReasons | warning/error |
| **边界态** | 部分 Agent 缺失但当前 Agent 可用时不阻断 | 多 Agent 状态不一致 |

### 4.4 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| health API 自身失败 | `500` | “环境体检暂不可用” | 允许用户重试；不白屏 |
| workspace 不存在 | `WORKSPACE_MISSING` | “项目目录不存在” | 打开项目设置/重新选择 |
| workspace 不可写 | `WORKSPACE_NOT_WRITABLE` | “项目目录不可写，Agent 无法保存文件” | 用户修复权限后重试 |
| CLI 缺失 | `CLI_MISSING` | “未找到 Claude Code/Codex/OpenCode 可执行文件” | 去 AgentPanel 配置 |
| DeepSeek 未配置 | `SYSTEM_MODEL_MISSING` | “标题/总结/编辑辅助能力将降级” | 不阻断 CLI 对话 |

---

## 5. 前端页面设计

### 5.1 页面布局

```text
ProjectSidebar
├── Agent list
├── Project list
└── HealthCheckCard
    ├── Collapsed summary
    └── Expanded grouped items

ChatHeader
└── Health icon button (compact mirror)
```

左侧底部常驻一个紧凑体检卡。ChatHeader 可放一个只显示 overall 的 icon button，方便窄屏或左栏滚动时快速打开。

### 5.2 组件树

```text
HealthCheckCard
├── HealthSummary
├── HealthItemGroup[]
│   └── HealthItemRow[]
└── RefreshHealthButton

stores/
└── systemStore.ts
```

### 5.3 关键视觉元素

| 元素 | 位置 | 视觉规格 |
|------|------|---------|
| overall 图标 | HealthCheckCard header | ok `CheckCircle2`，warning `AlertCircle`，error `OctagonAlert` |
| 检测项行 | 展开列表 | 24-32px 高度，左状态点，中间 label/detail，右 action icon |
| 去配置按钮 | 异常 CLI 项 | lucide `Settings` icon button，tooltip “打开 Agent 配置” |
| 刷新按钮 | Card footer/header | lucide `RefreshCw`，loading 时旋转 |

---

## 6. 前端交互序列

```text
用户: 进入 Project
  → 前端: systemStore.fetchHealth(projectId)
  → 后端: 聚合 Agent/Runtime/Workspace/SystemModel
  → 前端: HealthCheckCard 显示 overall

用户: 点击发送
  → 前端: systemStore.checkBeforeSend(sessionId, agentId)
  → 如果 blockingReasons 非空:
       阻断发送，ChatInput 上方显示错误条
     否则:
       继续 useSendMessage

用户: 点击异常项“去配置”
  → 前端: 切换到 AgentPanel 或 Project 设置
```

---

## 7. 验收标准

- [ ] AC-7C-01: `/api/system/health` 在未传 projectId/sessionId 时仍返回系统级状态，不 500。
- [ ] AC-7C-02: 传入 projectId 时，workspace 不存在或不可写会进入 `blockingReasons`。
- [ ] AC-7C-03: 缺失当前会话 Agent executable 时，发送按钮阻断并显示 CLI 缺失提示。
- [ ] AC-7C-04: DeepSeek API Key 未配置只显示 warning，不阻断 CLI 对话。
- [ ] AC-7C-05: 返回 payload 不包含任何 API key 值或敏感 env 值。
- [ ] AC-7C-06: HealthCheckCard 覆盖 loading/ok/warning/error/empty 状态。
- [ ] AC-7C-07: AgentPanel 修改 executable 后，刷新体检能反映新状态。

---

## 8. 测试策略

### 8.1 单元测试（10 条）

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| SystemHealthService | 4 | overall 聚合、blockingReasons、敏感信息过滤 |
| Workspace probe | 2 | missing/not writable |
| Runtime probe | 2 | node/python timeout/fallback |
| Agent probe | 2 | ready/not_found/codex config |

### 8.2 集成测试

- mock PATH 缺失 Claude Code → health missing → Chat send guard 阻断。
- 临时只读 workspace → health error/blocking。
- DeepSeek 未配置 → warning 但 `blockingReasons=[]`。

### 8.3 E2E 测试

- 打开项目 → 展开 HealthCheckCard → 点击异常 CLI 去配置 → AgentPanel 可见。
- 当前 Agent executable 缺失 → 点击发送 → 输入框上方显示阻断提示，无 chat 请求发出。

---

## 9. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| CLI 工具由用户外部安装，系统只检测不安装 | ADR-0009 §配套决策 A |
| DeepSeek 仅作为内部系统模型展示降级，不进入用户 Agent 配置 | CONTEXT 领域规则；SystemLLMService |
| Health 是快照，不写库 | 环境状态可变，避免历史污染 |

---

## 10. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| CliAgentRegistry | executable_status | 已就绪 |
| CodexLocalConfigService | status | 已就绪 |
| ProjectService | project/workspace path | 已就绪 |
| SystemLLMService | system_model_status | 已就绪 |
| cli_runtime_registry | active_snapshots | 已就绪，统一覆盖短进程、stdin JSONL 常驻进程和会话级常驻 RPC 进程 |

---

## 11. Non-Goals

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不自动安装 CLI/Node/Python | 本机权限与平台差异过大 | 用户/安装文档 |
| 不保存系统凭据 | 安全边界 | 用户本机 CLI |
| 不检测 Docker/云沙箱 | P1 本机版不依赖 | P2 |
| 不阻断所有 warning | 避免过度妨碍聊天 | Chat guard 只看 blockingReasons |

---

## 12. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| Agent 可用性 | 分散在 `/api/agents` | `/api/system/health` 聚合展示 | 保留旧字段，新增聚合 API |
| 发送前校验 | 启动 CLI 后失败 | 发送前 health guard | 前端 ChatInput 接入 |
| DeepSeek 状态 | 后端内部错误 | UI 显示系统能力降级 | 不暴露密钥 |

> **版本历史**
> - v1.0 (2026-06-03): 旧版环境体检卡片。
> - v2.0 (2026-06-06): 按当前 CLI Agent/Project/SystemLLM 实现重构，新增统一 health payload 和发送前 guard。
> - v2.1 (2026-06-06): 同步环境体检实现基线与验收状态。

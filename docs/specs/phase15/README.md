# Phase 15：真实云 Sandbox Runtime

**版本**: v0.1  
**创建日期**: 2026-06-09  
**状态**: Planned  
**关联 ADR/PRD**: [AgentHub-多Agent协作平台设计](../../archive/AgentHub-多Agent协作平台设计.md)、[ADR-0005](../../adr/0005-target-architecture.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[PRD-01](../../PRD/01-Architecture_Adapter.md)、[PRD-02](../../PRD/02-Orchestrator_Engine.md)、[PRD-07](../../PRD/07-SaaS_Cloud_Workspace_Delivery.md)  
**依赖模块**: Phase 10 Sandbox Runner 与云端 Agent Runtime、Phase 14 生产 Auth 与租户隔离收口

> Phase 15 把 Phase 10 的本机模拟 cloud runtime 替换为生产级云端隔离运行时。它必须继续遵守 CLI Wrapper 事件契约：AgentHub 仍然封装真实 CLI 工具，而不是裸调 HTTP LLM API。

---

## 1. 目标

Phase 10 已经打通 `cloud Project -> sandbox ready -> CLI 输出 -> Artifact/logs/run 终态` 的可替换切片，但当前 cloud workspace 和 sandbox 仍由本机目录与本机 subprocess 模拟。Phase 15 的目标是把这条链路迁移到真实云运行环境：每次 Agent run 在隔离容器或 microVM 中执行，挂载当前租户 workspace，受资源、网络、secret 和生命周期策略约束。

**成功标准**（可证伪）：

- [ ] cloud run 不再使用应用服务器本机目录和本机 subprocess 作为生产执行路径。
- [ ] 每个 sandbox 运行在独立容器、Kubernetes Job、Firecracker/microVM 或等价隔离环境中。
- [ ] Workspace 以隔离卷或对象存储 materialize 到 sandbox，运行结束后安全同步回 cloud workspace。
- [ ] CPU、内存、磁盘、运行时长、并发数、网络出口策略和空闲回收在 runner 层真实生效。
- [ ] Secret 只在 sandbox 内按需注入；日志、事件、Artifact metadata 中不泄漏原始 secret。
- [ ] 取消 run 能终止真实容器/进程并持久化 `cancelled`；异常退出能保留日志和错误摘要。
- [ ] 两个租户的 sandbox 无法互读 workspace、环境变量、日志、artifact 或网络凭据。
- [ ] P1 Local Desktop 的本机 CLI runtime 不受影响，仍然通过 localhost 后端访问本机目录。
- [ ] 不通过标准：只把本机目录换名为 cloud；或容器共享宿主目录且无租户隔离；或 Agent 改为裸 LLM API。

---

## 2. 全局定位

```text
Phase 14 Production Auth + TenantScope
  -> [Phase 15: RunnerProvider + workspace volume + real sandbox lifecycle]
  -> Phase 16 Production Deployment Provider
```

Phase 15 是 SaaS 版能否承载真实用户代码执行的关键阶段。它优先解决执行隔离与可靠性，不负责公网发布域名和 CDN。

---

## 3. 范围

### 3.1 必做

- 新增 `RunnerProvider` 抽象，支持本地开发 runner 与生产 runner 分离。
- 生产 runner 至少支持一种真实隔离后端：Docker、Kubernetes Job 或 microVM。
- Workspace materialization：运行前拉取/挂载 workspace，运行中读写，运行后同步 diff/snapshot。
- 镜像与工具链管理：定义默认 CLI image，包含 Claude Code、Codex、OpenCode 或可配置安装步骤。
- 运行队列和调度：并发限制、排队、超时、取消、失败重试。
- 日志流：stdout/stderr/system log 按 sequence 持久化并通过现有 SSE/WebSocket 事件返回。
- Secret 注入和脱敏：按 project/team/user scope 注入，日志统一 redaction。
- 网络策略：默认禁用或限制出口；允许按 workspace/agent policy 开启必要域名。
- 运维健康：runner node 心跳、容量、失败率、清理任务。

### 3.2 非目标

- 不实现真实一键部署；Phase 16 负责。
- 不实现计费套餐；只保留 quota/usage 扩展点。
- 不重写 CLI Adapter；继续复用 Phase 6/7 的真实 CLI 事件契约。
- 不把本地桌面端迁移到云端执行。

---

## 4. 核心设计

### 4.1 RunnerProvider

```python
class RunnerProvider:
    async def create_sandbox(self, request: SandboxRequest) -> SandboxHandle: ...
    async def start_process(self, sandbox: SandboxHandle, command: RuntimeCommand) -> ProcessHandle: ...
    async def stream_logs(self, process: ProcessHandle): ...
    async def cancel(self, sandbox_id: str, reason: str | None = None) -> None: ...
    async def collect_workspace_diff(self, sandbox_id: str) -> WorkspaceDiff: ...
    async def dispose(self, sandbox_id: str) -> None: ...
```

`CloudAgentRuntimeService` 只依赖 `RunnerProvider`，不直接操作 Docker/Kubernetes SDK，也不直接拼接宿主机路径。

### 4.2 Workspace 挂载模型

```text
cloud://agenthub/workspaces/{workspaceId}
  -> WorkspaceStorageProvider
      -> materialize to isolated volume
          -> RunnerProvider mounts volume read/write
              -> run CLI Agent
          -> collect diff/snapshot
      -> persist back to cloud storage
```

生产环境中，`cloud://` 是唯一对上层可见的 workspace 标识。服务器物理路径、容器挂载路径和对象存储 bucket/key 都不能出现在前端响应里。

### 4.3 生命周期

```text
queued
  -> provisioning
  -> ready
  -> running
  -> syncing
  -> completed | failed | cancelled | timed_out
  -> disposed
```

`disposed` 表示运行环境已销毁，不代表日志和 workspace diff 被删除。日志、run 记录和 Artifact 必须继续可查。

---

## 5. 跨模块契约

### 5.1 API 端点

Phase 15 复用 Phase 10 的主要 API，并补充运行镜像和 runner 状态：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/sandboxes` | POST | 创建真实 sandbox；必须校验租户权限和 quota |
| `/api/sandboxes/{sandboxId}` | GET | 查询 sandbox 生命周期、runner node、资源摘要 |
| `/api/sandboxes/{sandboxId}/stop` | POST | 取消并销毁真实运行环境 |
| `/api/sessions/{sessionId}/runs` | POST | cloud runtime 走生产 runner；local runtime 保持本机路径 |
| `/api/runs/{runId}/logs` | GET | 返回持久化 stdout/stderr/system log |
| `/api/runtime/images` | GET | 返回当前租户可用的 Agent runtime image |
| `/api/runtime/runner-nodes` | GET | 管理员查询 runner node 健康与容量 |

### 5.2 数据库变更

```sql
CREATE TABLE runner_nodes (
  id VARCHAR PRIMARY KEY,
  provider VARCHAR NOT NULL,
  region VARCHAR,
  status VARCHAR NOT NULL,
  capacity_json TEXT NOT NULL,
  last_heartbeat_at DATETIME,
  created_at DATETIME NOT NULL
);

CREATE TABLE workspace_volumes (
  id VARCHAR PRIMARY KEY,
  workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
  storage_provider VARCHAR NOT NULL,
  storage_uri TEXT NOT NULL,
  status VARCHAR NOT NULL,
  last_synced_at DATETIME,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

ALTER TABLE sandboxes ADD COLUMN provider VARCHAR;
ALTER TABLE sandboxes ADD COLUMN external_id VARCHAR;
ALTER TABLE sandboxes ADD COLUMN region VARCHAR;
ALTER TABLE sandboxes ADD COLUMN disposed_at DATETIME;

ALTER TABLE runtime_runs ADD COLUMN queued_at DATETIME;
ALTER TABLE runtime_runs ADD COLUMN sync_completed_at DATETIME;
```

### 5.3 事件

| 事件类型 | payload |
|---------|---------|
| `sandbox.provisioning` | `{ sandboxId, workspaceId, provider, image }` |
| `sandbox.ready` | `{ sandboxId, runnerNodeId, resourceLimits }` |
| `sandbox.resource.updated` | `{ sandboxId, cpuMs, memoryMb, diskMb, networkBytes }` |
| `runtime.log` | `{ runId, sequence, stream, text }` |
| `workspace.sync.started` | `{ workspaceId, sandboxId, runId }` |
| `workspace.sync.completed` | `{ workspaceId, sandboxId, changedFiles }` |
| `sandbox.disposed` | `{ sandboxId, reason }` |

---

## 6. 安全与隔离要求

| 风险 | 要求 |
|------|------|
| 跨租户文件读取 | 每个 sandbox 只能挂载自己的 workspace volume；禁止共享可写宿主路径 |
| Secret 泄漏 | Secret 注入走临时文件或环境变量；日志进入 EventBus 前必须脱敏 |
| 网络滥用 | 默认网络策略最小化；按 provider allowlist 开启 |
| 资源耗尽 | runner 层设置 CPU/memory/disk/time limit；超限必须终止 |
| 运行残留 | sandbox 结束后销毁容器和临时卷；保留持久化日志和 workspace diff |
| 供应链风险 | runtime image 固定版本、可审计、可回滚 |

---

## 7. 验收矩阵

| 验收项 | 方法 | 通过标准 |
|--------|------|---------|
| 真实隔离运行 | 真实服务 E2E | run 在容器/K8s/microVM 中执行，非应用服务器本机 subprocess |
| Workspace 同步 | E2E + 文件断言 | Agent 修改文件后 cloud workspace 持久化，Artifact 正常创建 |
| 跨租户隔离 | 安全测试 | 租户 A 无法读取租户 B workspace/secret/log |
| 资源限制 | 故障注入 | 超时、内存、磁盘、并发超限均产生可诊断终态 |
| 取消与清理 | E2E | 用户取消后进程终止、sandbox disposed、日志保留 |
| Secret 脱敏 | 日志测试 | 原始 secret 不出现在 RuntimeLog、SSE、Artifact metadata |
| P1 零回归 | 三端验收 | Local Desktop 本机 CLI runtime 不受生产 runner 影响 |

---

## 8. 完成后的解锁项

- SaaS Web 可以承载真实用户代码执行，而不是开发态模拟。
- Mobile 审批可以控制真实云端 run。
- Phase 16 可以基于真实 cloud workspace 和 build runner 做公网发布。
- 运维侧可以监控 runner 容量、失败率、资源使用和清理状态。

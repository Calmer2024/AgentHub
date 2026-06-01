# 05 — 协作交互设计

**Grill 决议**: 混合 DAG 模式 + 面板气泡混合渲染 + 对话流共享 + 定向注入
**关联前端**: `CollaborationView.tsx` (当前), `CollaborationPanel` (最终目标)

---

## 1. 核心理念

```
❌ 当前: Orchestrator 分发给 N 个 Agent → 各自独立回复 → 互不知晓
       这是多路复用，不是协作

✅ 目标: 多个 Agent 像群聊成员一样依次回复各自的产出
       可以并行完成不同任务，也可以串行完成有依赖的任务
       全程由 Orchestrator 调度
```

## 2. 前端渲染模型: 面板 + 气泡混合

| 组件 | 内容 | 何时可见 |
|------|------|---------|
| **CollaborationPanel** | DAG 流程图: Phase 节点 + 依赖箭头 + 实时状态 | 协作触发即显示，完成后自动折叠 |
| **Agent 聊天气泡** | 每个 Agent 完整产出，带角色标签 + agent 名称 | Phase 开始时创建，流式填充 |
| **错误气泡** | Agent 失败时的错误信息 | Agent 失败时 |

### 2.1 渲染时序

```
用户发送 "帮我做登录系统，先设计方案再前后端分别实现，最后审查"

  t=0.0s    Orchestrator 横幅: "代码生成 · 4 个 Agent"
  
  t=0.5s    CollaborationPanel 出现, DAG 可见:
            ┌─ Phase 0 ─┐    ┌─ Phase 1 ──────┐    ┌─ Phase 2 ──┐
            │ 📐 规划者   │ →  │ ⚡ 前端 (并行)  │ →  │ 🔍 审查者   │
            │   pending  │    │ ⚡ 后端 (并行)  │    │   pending  │
            └────────────┘    └────────────────┘    └────────────┘

  Phase 0 (串行):
  t=2.0s    @架构师 [规划者] 气泡出现, 流式打字 "我来分析需求..."
  t=8.0s    @架构师 完成, Phase 0 → ✅

  Phase 1 (并行 — 两个气泡同时出现!):
  t=8.5s    @前端专家 [执行者] 气泡同时出现, 流式 "我来实现前端部分..."
  t=8.5s    @后端架构师 [执行者] 气泡同时出现, 流式 "我来实现后端 API..."
  t=15s     @后端架构师 先完成 ✅
  t=18s     @前端专家 完成, Phase 1 → ✅

  Phase 2 (串行):
  t=18.5s   @代码审查员 [审查者] 气泡出现, 流式 "审查结果: ..."
  t=25s     @代码审查员 完成, Phase 2 → ✅

  t=25s     协作完成, Panel 自动折叠, 最终消息显示
```

### 2.2 并行气泡渲染规则

| 规则 | 实现 |
|------|------|
| 同时出现 | 同一 Phase 的所有 Agent 气泡**同时创建** (一个 React render 周期内) |
| 独立流式 | 每个气泡独立接收 token (通过 `agentId` 路由) |
| 自然排序 | Phase 内按角色优先级: planner > executor > reviewer > researcher > synthesizer > critic |
| 视觉区分 | 左侧彩色竖线 + 角色标签 badge |
| 无遮挡 | 气泡在消息流的自然位置，不使用 absolute 定位 |

### 2.3 Agent 聊天气泡格式

```
┌─────────────────────────────────────────┐
│ ┃ @前端专家  [执行者]                     │  ← 彩色竖线 + 角色 badge
│ ┃                                        │
│ ┃ 收到规划者的方案。我来实现前端部分:       │
│ ┃ ```tsx                                 │
│ ┃ const LoginPage = () => {              │
│ ┃   // ...                               │
│ ┃ }                                      │
│ ┃ ```                                    │
│ ┃                                        │
│ ┃ 如上所示，登录页面包含表单验证和...       │
└─────────────────────────────────────────┘
```

### 2.4 CollaborationPanel 设计

```
┌─ Orchestrator · 代码生成 · 4 Agent ──────────────────────┐
│                                                            │
│  ┌─ Phase 0 ──────────┐     ┌─ Phase 1 ────────────┐      │
│  │ 📐 规划者           │ ─→  │ ⚡ 前端专家 (并行)    │      │
│  │   @架构师           │     │ ⚡ 后端架构师 (并行)  │      │
│  │   ✅ 已完成 (8s)    │     │   ✅ 已完成          │      │
│  └────────────────────┘     └──────────────────────┘      │
│                                      │                     │
│                                      ▼                     │
│                            ┌─ Phase 2 ──────────┐         │
│                            │ 🔍 审查者           │         │
│                            │   @代码审查员       │         │
│                            │   ● 运行中...      │         │
│                            └────────────────────┘         │
│                                                            │
│  默认折叠，点击展开。完成后 10s 自动折叠。                    │
└────────────────────────────────────────────────────────────┘
```

---

## 3. 上下文共享机制

### 3.1 双层策略

| 层级 | 机制 | 范围 | 注入方式 |
|------|------|------|---------|
| **对话流共享** | Agent 产出实时追加到共享 messages | 所有 Agent 可见 | `[{role:"assistant", content:"[planner] @架构师:\n..."}]` |
| **定向注入** | depends_on 前驱的完整产出 | 仅后继可见 | `[{role:"assistant", content:"[上一步完整产出]\n{3000 chars}"}]` |

### 3.2 SharedContext 实现

```python
class SharedContext:
    def __init__(self, base_messages):
        self.messages = list(base_messages)
        self.agent_outputs: dict[str, str] = {}  # task_name → full_output

    def append_output(self, task_name, agent_name, role, content):
        self.agent_outputs[task_name] = content
        self.messages.append({
            "role": "assistant",
            "content": f"[{role}] @{agent_name}:\n{content}",
        })

    def get_for_agent(self, depends_on: list[str]) -> list[dict]:
        msgs = list(self.messages)
        for dep in depends_on:
            output = self.agent_outputs.get(dep, "")
            if output:
                msgs.append({
                    "role": "assistant",
                    "content": f"[上一步 ({dep}) 完整产出]\n{output[:3000]}",
                })
        return msgs
```

### 3.3 各 Agent 视角

```
Planner 看到的:
  [用户消息]
  
Executor-A (前端) 看到的:
  [用户消息]
  + [planner] @架构师: 方案内容...
  + [上一步 (planning) 完整产出]\n{方案全文}

Executor-B (后端) 看到的:
  [用户消息]  
  + [planner] @架构师: 方案内容...
  + [上一步 (planning) 完整产出]\n{方案全文}

Reviewer 看到的:
  [用户消息]
  + [planner] @架构师: ...
  + [executor] @前端专家: ...
  + [executor] @后端架构师: ...
  + [上一步 (frontend) 完整产出]\n{前端全文}
  + [上一步 (backend) 完整产出]\n{后端全文}
```

---

## 4. 当前实现状态

| 功能 | 状态 | 备注 |
|------|------|------|
| 面板+气泡混合渲染 | ⚠️ 部分 | CollaborationView 面板存在但无 DAG 图；气泡无角色标签 |
| 并行同时流式 | ✅ | placeholder 同时创建 |
| 上下文共享 | ❌ 未实现 | 所有 Agent 收到同一份 input_messages |
| 定向注入 | ⚠️ 部分 | chain 模式有产出注入，但无 SharedContext 抽象 |
| CollaborationPanel DAG 图 | ❌ 未实现 | 当前 CollaborationView 只展示简单任务列表 |
| Agent 聊天气泡 (角色标签) | ❌ 未实现 | 当前气泡无 role badge |

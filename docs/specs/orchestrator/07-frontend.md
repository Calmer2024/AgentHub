# 07 — 前端组件

**关联实现**: `frontend/src/components/CollaborationView.tsx`, `ChatWindow.tsx`, `GroupChatCreator.tsx`, `App.tsx`

---

## 1. 组件架构

```
App.tsx
├── Sidebar
│   ├── SessionList        (会话列表, 新建群聊入口)
│   ├── AgentPanel         (Agent 管理)
│   └── SettingsPanel      (API Key 配置)
│
├── ChatWindow             (主聊天区域)
│   ├── Header             (标题 + Agent 选择器 + 流式指示器)
│   ├── Orchestrator 横幅  (route + intent 标签)
│   ├── CollaborationPanel (DAG 流程图 + 状态 ❌ 当前为 CollaborationView)
│   ├── Agent 聊天气泡     (每个 Agent 的产出, 带角色标签)
│   ├── MessageBubble       (普通消息气泡)
│   └── ChatInput           (@mention 输入框)
│
└── GroupChatCreator       (群聊创建弹窗 — 无链式开关)
```

## 2. CollaborationView (当前) → CollaborationPanel (目标)

### 2.1 当前: CollaborationView

**文件**: `CollaborationView.tsx`

```
功能:
  · 展示任务列表 (name + role + agent + status)
  · 链式步骤流 (chain_step 驱动)
  · 可折叠/展开
  · 内联渲染 (在 ChatWindow 消息区域上方, 不使用 absolute 定位)

Props:
  intent, tasks, chainSteps, isCompleted, completedSummary, children
```

### 2.2 目标: CollaborationPanel

需要升级的内容:

| 当前 | 目标 |
|------|------|
| 任务列表 | DAG 流程图 (Phase 节点 + 箭头) |
| chainSteps 状态驱动 | phases DAG + phase_change 驱动 |
| 简单状态圆点 | Phase 进度条 + 完成/运行/等待动画 |
| 无依赖展示 | 箭头连接各 Phase 节点 |
| 完成后折叠 | 完成后 10s 自动折叠 |

## 3. Agent 聊天气泡

### 3.1 当前

每个 Agent 产出渲染为普通 `MessageBubble` (无角色信息)。

### 3.2 目标

新增 `agentName`、`role`、`phase` 字段到 MessageBubble:

```typescript
interface MessageBubbleProps {
  message: Message;
  isStreaming: boolean;
  // 新增
  agentRole?: string;       // "planner" | "executor" | ...
  phase?: number;           // 所属 Phase
  isCollaborating?: boolean; // 是否在协作中 (彩色竖线 + badge)
}
```

### 3.3 视觉规范

```
普通消息气泡:
┌─────────────┐
│  消息内容    │
└─────────────┘

协作 Agent 气泡:
┃ ┌─ @前端专家 [执行者] Phase 1 ─────────┐
┃ │  实现前端登录页面...                    │  ← 左侧彩色竖线 (角色颜色)
┃ │  ```tsx ... ```                       │
┃ └──────────────────────────────────────┘

角色颜色映射:
  planner    → 紫色
  executor   → 蓝色
  reviewer   → 橙色
  researcher → 绿色
  synthesizer → 青色
  critic     → 红色
```

## 4. ChatWindow

### 4.1 Props (完整)

```typescript
interface Props {
  // 基础
  messages: Message[];
  isStreaming: boolean;
  streamingError: string | null;
  currentAgent: AgentConfig | null;
  agents: AgentConfig[];
  mode: string;
  mentionableAgents: AgentConfig[];

  // Orchestrator
  routeAgents: RouteAgent[] | null;
  orchestratorIntent: string | null;

  // 协作面板
  collabTasks: CollabTask[];
  chainSteps: ChainStep[];
  collabCompleted: boolean;
  collabSummary: string | null;

  // 回调
  onSend: (content: string, mentions: string[]) => void;
  onDismissError: () => void;
  onSwitchAgent: (agentId: string) => void;
}
```

### 4.2 布局顺序 (自然流, 无 absolute 定位)

```
┌─────────────────────────────────────┐
│ Header: 群聊 | 流式指示器            │
├─────────────────────────────────────┤
│ [若群聊] @提及 Agent 提示            │
├─────────────────────────────────────┤
│ [若有路由] Orchestrator 横幅:        │
│   代码生成 → @架构师 @前端专家       │
├─────────────────────────────────────┤
│ [若有协作] CollaborationPanel:      │  ← 内联渲染
│   Phase 0 → Phase 1 → Phase 2       │
├─────────────────────────────────────┤
│ [若有错误] 红色横幅 + 关闭按钮        │
├─────────────────────────────────────┤
│ 消息区域 (scrollable):               │
│   · 用户消息气泡                     │
│   · Agent A 气泡 [规划者]            │
│   · Agent B 气泡 [执行者]            │
│   · Agent C 气泡 [审查者]            │
├─────────────────────────────────────┤
│ [单聊] Agent 选择器                  │
├─────────────────────────────────────┤
│ ChatInput: @mention 输入框 + 发送     │
└─────────────────────────────────────┘
```

## 5. GroupChatCreator

**自动化优先**: 无链式开关，用户只需选择 2-5 个 Agent。Orchestrator 自动决定协作模式。

```typescript
interface Props {
  agents: AgentConfig[];
  onConfirm: (title: string, selectedIds: string[]) => void;
  onCancel: () => void;
}
```

## 6. App.tsx — 协作状态管理

### 6.1 状态持久化 (Zustand chatStore)

协作状态按 `sessionId` 隔离存储。切换会话 → 保存当前 + 恢复目标。

```typescript
interface CollabSnapshot {
  routeAgents: RouteAgent[] | null;
  collabTasks: CollabTask[];
  chainSteps: ChainStep[];
  orchestratorIntent: string | null;
  collabCompleted: boolean;
  collabSummary: string | null;
}

// store:
collabSnapshots: Record<string, CollabSnapshot>;
getCollab(sessionId) → CollabSnapshot;
saveCollab(sessionId, snap) → void;
```

### 6.2 SSE 回调链

```typescript
createChatStream(sessionId, content, mentions, {
  onRoute: (agents) → saveCollab(..., {routeAgents: agents}),
  onTaskStarted: (tasks, intent) → saveCollab(..., {collabTasks: tasks, orchestratorIntent: intent}),
  onChainStep: (step) → saveCollab(..., {chainSteps: updatedSteps, collabTasks: updatedTasks}),
  onTaskCompleted: (summary) → saveCollab(..., {collabCompleted: true, collabSummary: summary}),
  onAgentToken: (agentId, name, token) → appendAgentStreamingToken(localId, name, token),
})
```

## 7. 当前实现状态

| 组件 | 状态 | 备注 |
|------|------|------|
| CollaborationView | ✅ | 基础面板 (任务列表 + 状态) |
| CollaborationPanel (DAG) | ❌ | 需重写为 DAG 流程图 |
| Agent 聊天气泡 (角色标签) | ❌ | 需扩展 MessageBubble |
| ChatWindow 内联布局 | ✅ | 已修复 absolute 重叠 |
| GroupChatCreator (无开关) | ✅ | 自动化优先 |
| App.tsx 协作状态持久化 | ✅ | chatStore collabSnapshots |
| SSE 回调链路 | ✅ | onRoute/onTaskStarted/onChainStep/onTaskCompleted |

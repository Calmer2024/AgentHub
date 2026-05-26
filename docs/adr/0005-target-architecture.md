# ADR-0005: 目标架构与接口契约

**Date**: 2026-05-25
**Status**: Accepted

## Context

根据 ADR-0004 的架构跑道原则，需要在动手写代码之前确定目标架构图和各层职责，作为所有增量开发的"北星"。实际实现按触发条件逐步引入各层，Day 1 不必全部构建。

## Decision

### 目标架构图（七层）

```
┌──────────────────────────────────────────────────────┐
│                  Frontend Layer                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ UI Components│  │ State Store │  │ WS Client     │  │
│  │ (shadcn/ui) │  │ (Zustand)  │  │ (heartbeat,    │  │
│  │             │  │            │  │  reconnect)    │  │
│  └────────────┘  └────────────┘  └────────────────┘  │
├──────────────────────────────────────────────────────┤
│                API Gateway Layer                      │
│  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │ REST Endpoints   │  │ WebSocket Manager         │ │
│  │ (thin: validate, │  │ (auth, connect,           │ │
│  │  delegate,       │  │  broadcast per session)   │ │
│  │  serialize)      │  │                           │ │
│  └────────┬─────────┘  └─────────────┬─────────────┘ │
├───────────┼─────────────────────────┼───────────────┤
│           ▼                         ▼                │
│              Service / Business Logic Layer           │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ Session  │ │ Message  │ │ Artifact             │ │
│  │ Service  │ │ Service  │ │ Service              │ │
│  │          │ │          │ │ (store, preview,     │ │
│  │          │ │          │ │  deploy, versioning) │ │
│  └────┬─────┘ └────┬─────┘ └──────────┬───────────┘ │
├───────┼─────────────┼─────────────────┼─────────────┤
│       ▼             ▼                 ▼              │
│                Domain / Core Layer                     │
│  ┌────────────────────┐  ┌──────────────────────────┐│
│  │ Orchestrator       │  │ Context / Prompt Manager ││
│  │ - intent analysis  │  │ - prompt assembly        ││
│  │ - task decomposition│  │ - token estimation       ││
│  │ - parallel dispatch│  │ - history compression    ││
│  │ - result aggregation│  │ - pin priority system   ││
│  │ - failure fallback │  │ - system prompt injection││
│  └────────┬───────────┘  └─────────────┬────────────┘│
├───────────┼────────────────────────────┼─────────────┤
│           ▼                            ▼             │
│              Infrastructure Layer                      │
│  ┌──────────┐ ┌────────────┐ ┌────────────────────┐  │
│  │ Agent    │ │ Event Bus  │ │ File / Storage     │  │
│  │ Adapters │ │ (pub/sub,  │ │ Manager            │  │
│  │          │ │  async)    │ │ (local→S3, cleanup)│  │
│  └──────────┘ └────────────┘ └────────────────────┘  │
├──────────────────────────────────────────────────────┤
│              Data / Persistence Layer                  │
│  ┌──────────────┐  ┌───────────────────────────────┐ │
│  │ Models (ORM) │  │ Configuration Store            │ │
│  │ SQLAlchemy   │  │ (Agent prompts, API keys,      │ │
│  │              │  │  tool definitions, user prefs) │ │
│  └──────────────┘  └───────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### 各层职责与 Phase 引入时机

| 层 | 职责 | Day 1 实现？ | 引入时机 |
|----|------|------------|---------|
| **Frontend** | UI 渲染 + 状态管理 + WS 通信 | 部分（无 WS） | Phase 1 做基础组件，Phase 2.2 加 WS Client |
| **API Gateway** | 路由参数校验 → 委托 Service → 序列化响应 | 是（但路由直接调 Agent） | Phase 1；Phase 2.2 重构为 thin handler |
| **Service** | 业务逻辑编排、事务管理、权限校验 | **否** | Phase 2.2（消息引用/重生成/多 Agent 时引入） |
| **Domain** | Orchestrator 调度 + Prompt 管理 | **否** | Phase 2.3（群聊）+ Phase 2.4（长上下文） |
| **Infrastructure** | Agent 适配 + 事件总线 + 文件存储 | 部分（仅 Agent 适配器） | Phase 1 只建 adapters；Event Bus 在 Phase 2.3 引入；File Manager 在 Phase 2.4 引入 |
| **Data** | ORM 模型 + 配置存取 | 部分（仅核心 models） | Phase 1 建 Session/Message/Agent 三张表；Config Store 随功能扩展逐步加入 |

### 依赖规则

1. **只能向下依赖**：上层可以依赖下层，下层绝不依赖上层
2. **同层不互依赖**：同一层的模块之间通过 Event Bus 或接口解耦通信
3. **Domain 层是纯逻辑**：不依赖任何框架（FastAPI、SQLAlchemy），只依赖接口/类型定义
4. **Infrastructure 层实现 Domain 定义的接口**：如 `BaseAgentAdapter` 定义在 Domain，实现在 Infrastructure

---

## Core Interface Contracts

以下接口契约在项目初期定义，所有实现必须遵守。

### 1. Agent Adapter Contract

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

@dataclass
class AgentCapability:
    """Agent 能力声明"""
    name: str
    supports_streaming: bool = True
    supports_file_input: bool = False
    supports_tool_call: bool = False
    max_context_tokens: int = 100_000
    tags: list[str] = field(default_factory=list)  # e.g. ["code", "writing"]

@dataclass
class AgentResponse:
    """Agent 单次回复"""
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = "stop"       # "stop" | "length" | "tool_call"
    usage: dict | None = None         # {"prompt_tokens": N, "completion_tokens": M}

class BaseAgentAdapter(ABC):
    """所有 Agent 平台适配器必须实现的接口。
    
    定义于 Domain 层，实现在 Infrastructure 层。
    """

    @property
    @abstractmethod
    def capability(self) -> AgentCapability:
        """返回该 Agent 的能力元信息"""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],           # [{"role": "user"|"assistant", "content": "..."}]
        system_prompt: str,
        on_token: Callable[[str], None] | None = None,  # 流式回调，为 None 则不流式
    ) -> AgentResponse:
        """发送消息并获取回复。若提供 on_token，则逐 token 回调。"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """流式发送消息，返回 token 迭代器。"""
        ...
```

### 2. Message Service Contract

```python
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

@dataclass
class MessageCreate:
    """创建消息的输入"""
    session_id: str
    role: str                        # "user" | "assistant" | "system"
    content: str
    content_type: str = "text"       # "text" | "code" | "diff" | "artifact_card"
    parent_message_id: str | None = None   # 被引用的消息
    metadata: dict | None = None

@dataclass  
class MessageRead:
    """消息的读取模型"""
    id: str
    session_id: str
    role: str
    content: str
    content_type: str
    parent_message_id: str | None
    created_at: datetime
    metadata: dict | None

class MessageService(ABC):
    """消息业务逻辑接口。
    
    Phase 2.2 引入。Phase 1 中此逻辑暂驻留在 API 路由中。
    """

    @abstractmethod
    async def send_message(self, input: MessageCreate) -> MessageRead:
        """发送一条消息：持久化 → 组装上下文 → 调用 Agent → 流式写回 → 返回完成的消息"""
        ...

    @abstractmethod
    async def send_message_stream(
        self, input: MessageCreate
    ) -> AsyncIterator[str]:
        """流式发送消息，yield 每个 token 块。用于 SSE/WebSocket 推送到前端。"""
        ...

    @abstractmethod
    async def get_session_messages(
        self, session_id: str, limit: int = 50, before: str | None = None
    ) -> list[MessageRead]:
        """获取会话历史消息，支持分页"""
        ...

    @abstractmethod
    async def regenerate_message(
        self, message_id: str
    ) -> MessageRead:
        """重新生成指定消息的回复"""
        ...
```

### 3. Event Bus Contract

```python
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Awaitable

class EventType(Enum):
    """系统事件类型。Phase 2.3 引入 Event Bus 时完整定义。"""
    MESSAGE_CREATED = "message.created"
    MESSAGE_STREAMING = "message.streaming"    # 流式输出中的 token 块
    MESSAGE_COMPLETED = "message.completed"
    ORCHESTRATOR_TASK_STARTED = "orchestrator.task.started"
    ORCHESTRATOR_TASK_COMPLETED = "orchestrator.task.completed"
    AGENT_CALL_STARTED = "agent.call.started"
    AGENT_CALL_COMPLETED = "agent.call.completed"
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

class EventBus(ABC):
    """事件总线接口。Phase 2.3 引入。"""

    @abstractmethod
    async def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """发布事件"""
        ...

    @abstractmethod
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """订阅事件"""
        ...

    @abstractmethod
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """取消订阅"""
        ...
```

### 4. Context Manager Contract

```python
from dataclasses import dataclass, field

@dataclass
class PromptAssemblyInput:
    """Context Manager 的输入"""
    session_id: str
    system_prompt: str
    messages: list[dict]              # 会话历史消息
    pinned_message_ids: list[str] = field(default_factory=list)
    max_tokens: int = 100_000         # 目标模型的最大 context window
    reserve_tokens: int = 4096        # 预留给回复的 token 数

@dataclass
class PromptAssemblyOutput:
    """Context Manager 的输出"""
    assembled_messages: list[dict]    # 组装后的消息列表（已截断、压缩）
    total_tokens: int                 # 预估总 token 数
    truncated: bool                   # 是否触发了截断
    pinned_included: list[str]        # 哪些 pinned 消息被成功包含

class ContextManager(ABC):
    """Prompt 上下文管理器接口。Phase 2.4 引入。"""

    @abstractmethod
    def assemble(self, input: PromptAssemblyInput) -> PromptAssemblyOutput:
        """组装发给 LLM 的最终 messages 列表。

        策略：
        1. System Prompt 固定在最前
        2. Pinned 消息按时间排序插入
        3. 剩余空间按 FIFO 填充最近历史
        4. 超出 max_tokens - reserve_tokens 的消息被截断或压缩
        """
        ...

    @abstractmethod
    def estimate_tokens(self, messages: list[dict]) -> int:
        """估算消息列表占用的 token 数"""
        ...
```

## Consequences

- 接口契约是**约束**，不是负担——它保证模块之间不会因实现细节变化而断裂
- 目标架构图是**北星**，不是蓝图——每次增量向它靠近，但允许中间态简化
- Layer 可以暂时合并（Phase 1 的 API 和 Service 合在一起），但不能反向依赖（Service 绝不能依赖 API）
- 每条 ADR 记录了"何时引入"的触发条件，避免提前过度设计

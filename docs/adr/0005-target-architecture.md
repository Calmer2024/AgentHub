# ADR-0005: 目标架构与接口契约

**Date**: 2026-05-25  
**Updated**: 2026-06-03 (重写为 CLI Wrapper 架构)  
**Status**: Accepted

## Context

根据 ADR-0004 的架构跑道原则，需要在动手写代码之前确定目标架构图和各层职责，作为所有增量开发的"北星"。实际实现按触发条件逐步引入各层，Day 1 不必全部构建。

> **架构路线修正 (2026-06-03)**: 本 ADR 原版定义了基于 HTTP LLM API 的 `BaseAgentAdapter` 接口（`chat()` / `chat_stream()` 接受 `messages: list[dict]`）。PRD-00 和 PRD-01 已正式推翻该路线，确立 CLI Wrapper 模式为 AgentHub 的唯一 Agent 架构。本次修订将接口契约从 HTTP API 调用全面重写为 CLI 进程管理（PTY/subprocess、stdin/stdout 桥接、ANSI 清洗、交互式拦截）。AgentHub 不做一个"调用大模型 API 的聊天室"，而是封装市面上真正具备独立执行能力的 CLI Agent 工具（Claude Code、OpenCode 等）的调度壳。

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
│  │          │ │          │ │  versioning, deploy) │ │
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
│  │ CLI      │ │ Event Bus  │ │ File / Storage     │  │
│  │ Agent    │ │ (pub/sub,  │ │ Manager            │  │
│  │ Adapters │ │  async)    │ │ (local→S3, cleanup)│  │
│  │ (Process │ │            │ │                    │  │
│  │  Manager)│ │            │ │                    │  │
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
| **API Gateway** | 路由参数校验 → 委托 Service → 序列化响应 | 是（路由直接调 Agent） | Phase 1；Phase 2.2 重构为 thin handler |
| **Service** | 业务逻辑编排、事务管理、权限校验 | **否** | Phase 2.2（消息引用/重生成/多 Agent 时引入） |
| **Domain** | Orchestrator 调度 + Prompt 管理 | **否** | Phase 2.3（群聊）+ Phase 2.4（长上下文） |
| **Infrastructure** | CLI Agent 进程管理 + 事件总线 + 文件存储 | 部分（仅 CLI 适配器核心） | Phase 1 只建 CLI 进程管理骨架；Event Bus 在 Phase 2.3 引入；File Manager 在 Phase 2.4 引入 |
| **Data** | ORM 模型 + 配置存取 | 部分（仅核心 models） | Phase 1 建 Session/Message/Agent 三张表；Config Store 随功能扩展逐步加入 |

### 依赖规则

1. **只能向下依赖**：上层可以依赖下层，下层绝不依赖上层
2. **同层不互依赖**：同一层的模块之间通过 Event Bus 或接口解耦通信
3. **Domain 层是纯逻辑**：不依赖任何框架（FastAPI、SQLAlchemy），只依赖接口/类型定义
4. **Infrastructure 层实现 Domain 定义的接口**：如 `BaseAgentAdapter` 定义在 Domain，实现在 Infrastructure

---

## Core Interface Contracts

以下接口契约在项目初期定义，所有实现必须遵守。

### 1. Agent Adapter Contract (CLI Wrapper)

AgentHub 的 Agent 适配器不是 HTTP API 调用，而是对真实 CLI 工具的进程封装。所有 Agent 适配器必须实现此接口。

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable

class AgentType(str, Enum):
    """Agent 执行类型"""
    CLI_WRAPPER = "cli_wrapper"       # 通过 PTY/subprocess 管理真实 CLI 工具
    ORCHESTRATOR = "orchestrator"     # 内置调度器（通过 LLM API 做意图分析/拆解）

@dataclass
class AgentCapability:
    """Agent 能力声明"""
    name: str
    executable: str                   # CLI 可执行文件名，如 "claude"、"opencode"
    supports_streaming: bool = True
    supports_file_io: bool = True     # CLI Agent 默认支持读写 workspace 文件
    supports_interactive_prompt: bool = True  # 是否支持 (y/n) 交互式拦截
    max_context_tokens: int = 100_000
    tags: list[str] = field(default_factory=list)

@dataclass
class AgentResponse:
    """Agent 单次执行回复"""
    content: str                      # 清洗后的纯文本/Markdown 内容
    raw_output: str | None = None     # 原始 stdout（调试用，可选保留）
    exit_code: int = 0
    events: list[dict] = field(default_factory=list)
    # events 中的标准事件类型：
    #   "agent.output"      — 流式文本块
    #   "artifact.detected" — 检测到产物（HTML/code block/patch/file change）
    #   "interactive_prompt"— CLI 发出的交互式确认请求
    #   "task_status_change"— 任务状态变更
    usage: dict | None = None

class BaseAgentAdapter(ABC):
    """所有 Agent 平台适配器必须实现的接口。
    
    定义于 Domain 层，实现在 Infrastructure 层。
    
    核心职责：管理一个真实 CLI 进程的完整生命周期——
    启动、stdin 写入、stdout/stderr 读取、ANSI 清洗、
    交互式提示拦截、超时/僵尸进程清理。
    """

    @property
    @abstractmethod
    def capability(self) -> AgentCapability:
        """返回该 Agent 的能力元信息"""
        ...

    @abstractmethod
    async def execute(
        self,
        prompt: str,                   # 注入给 CLI Agent 的系统/任务 prompt
        session_id: str,
        workspace_path: str,           # CLI 进程的 cwd（必须指向会话绑定的 workspace）
        on_token: Callable[[str], None] | None = None,
        env: dict | None = None,       # 环境变量注入（API Keys 等）
    ) -> AgentResponse:
        """启动 CLI 进程、发送 prompt、收集输出、返回完整回复。

        - 若提供 on_token，则逐 token 回调（经过 ANSI 清洗后）
        - 内部处理交互式拦截：匹配到 (y/n) 模式时暂停流推送，
          通过 EventBus 发出 interactive_prompt 信令，
          等待用户决策后以 stdin 注入回复
        """
        ...

    @abstractmethod
    async def execute_stream(
        self,
        prompt: str,
        session_id: str,
        workspace_path: str,
        env: dict | None = None,
    ) -> AsyncIterator[str]:
        """流式执行 CLI Agent，返回清洗后的 token 迭代器。"""
        ...

    @abstractmethod
    async def abort(self, session_id: str) -> None:
        """强制终止当前正在运行的 CLI 进程。
        
        发送 SIGTERM，超时 5s 后升级为 SIGKILL。
        """
        ...
```

### 2. CLI Process Manager Contract

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class CLIProcessConfig:
    """CLI 进程启动配置"""
    executable: str                   # 可执行文件路径，如 "claude" 或完整路径
    args: list[str]                   # 启动参数，如 ["--compact", "--theme=light"]
    cwd: str                          # 工作目录（会话 workspace_path）
    env: dict[str, str]               # 环境变量
    timeout_seconds: int = 300        # 静默超时（无 stdout 输出的最大秒数）
    heartbeat_timeout_seconds: int = 180  # 心跳超时（WS 断开后等待重连的最大秒数）

@dataclass
class StreamChunk:
    """从 CLI stdout 读取的一个数据块"""
    raw_bytes: bytes                  # 原始字节
    clean_text: str                   # ANSI 清洗后的纯净文本
    is_interactive: bool = False      # 是否检测到交互式提示 (y/n)
    interactive_content: str | None = None  # 交互式提示内容

class CLIProcessManager(ABC):
    """CLI 进程生命周期管理器接口。
    
    负责：PTY/subprocess 孵化、stdout/stderr 读取、
    ANSI 转义码清洗、交互式提示模式匹配、心跳/超时清理。
    """

    @abstractmethod
    async def spawn(self, config: CLIProcessConfig) -> str:
        """启动 CLI 进程，返回 process_id"""
        ...

    @abstractmethod
    async def write_stdin(self, process_id: str, data: str) -> None:
        """向进程 stdin 写入数据（用于注入用户回复、确认指令等）"""
        ...

    @abstractmethod
    async def read_stream(self, process_id: str) -> AsyncIterator[StreamChunk]:
        """流式读取 stdout，逐块 yield StreamChunk"""
        ...

    @abstractmethod
    async def terminate(self, process_id: str, force: bool = False) -> int:
        """终止进程。force=False 发 SIGTERM，force=True 发 SIGKILL。返回 exit_code"""
        ...

    @abstractmethod
    async def is_alive(self, process_id: str) -> bool:
        """检查进程是否仍在运行"""
        ...
```

### 3. Workspace Provider Contract

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class WorkspaceInfo:
    """Workspace 元信息"""
    workspace_id: str
    workspace_path: str              # 物理路径（本机）或 volume_key（云端）
    session_id: str
    session_title: str | None = None
    file_count: int = 0
    total_size_bytes: int = 0

@dataclass
class FileChange:
    """Workspace 文件变更事件"""
    workspace_id: str
    path: str                        # 相对于 workspace 根目录的路径
    change_type: str                 # "created" | "modified" | "deleted"
    diff_preview: str | None = None  # 变更的 diff 预览（文本文件）

class WorkspaceProvider(ABC):
    """Workspace 管理接口。
    
    P1（桌面版）由 LocalWorkspaceProvider 实现，直接操作本机文件系统。
    P2（SaaS 版）由 CloudWorkspaceProvider 实现，操作云端沙箱存储。
    """

    @abstractmethod
    async def create(self, session_id: str, path: str | None = None) -> WorkspaceInfo:
        """创建/绑定 workspace。path=None 则自动生成目录。"""
        ...

    @abstractmethod
    async def get(self, workspace_id: str) -> WorkspaceInfo:
        """获取 workspace 信息"""
        ...

    @abstractmethod
    async def list_files(self, workspace_id: str, subpath: str = "") -> list[dict]:
        """列出 workspace 中的文件"""
        ...

    @abstractmethod
    async def watch_changes(
        self, workspace_id: str
    ) -> AsyncIterator[FileChange]:
        """监听 workspace 文件变更（用于 Adapter 检测产物）"""
        ...

    @abstractmethod
    async def validate_path(self, workspace_id: str, relative_path: str) -> bool:
        """校验路径是否在 workspace 边界内（防越界）"""
        ...
```

### 4. Event Bus Contract

```python
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Awaitable

class EventType(Enum):
    """系统事件类型"""
    MESSAGE_CREATED = "message.created"
    MESSAGE_STREAMING = "message.streaming"
    MESSAGE_COMPLETED = "message.completed"
    ORCHESTRATOR_TASK_STARTED = "orchestrator.task.started"
    ORCHESTRATOR_TASK_COMPLETED = "orchestrator.task.completed"
    AGENT_PROCESS_STARTED = "agent.process.started"
    AGENT_PROCESS_COMPLETED = "agent.process.completed"
    AGENT_OUTPUT = "agent.output"               # 流式文本块
    ARTIFACT_DETECTED = "artifact.detected"     # CLI 输出中检测到产物
    ARTIFACT_CREATED = "artifact.created"
    ARTIFACT_UPDATED = "artifact.updated"
    INTERACTIVE_PROMPT = "interactive.prompt"   # CLI 发出交互式确认请求
    WORKSPACE_FILE_CHANGED = "workspace.file.changed"

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

### 5. Context Manager Contract

```python
from dataclasses import dataclass, field

@dataclass
class PromptAssemblyInput:
    """Context Manager 的输入"""
    session_id: str
    system_prompt: str
    messages: list[dict]
    pinned_message_ids: list[str] = field(default_factory=list)
    max_tokens: int = 100_000
    reserve_tokens: int = 4096

@dataclass
class PromptAssemblyOutput:
    """Context Manager 的输出"""
    assembled_messages: list[dict]
    total_tokens: int
    truncated: bool
    pinned_included: list[str]

class ContextManager(ABC):
    """Prompt 上下文管理器接口。Phase 2.4 引入。"""

    @abstractmethod
    def assemble(self, input: PromptAssemblyInput) -> PromptAssemblyOutput:
        """组装发送给 Agent 的最终 messages 列表。

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

- AgentHub 的 Agent 层是**进程管家**而非 HTTP 客户端：核心职责是 CLI 进程的启停、I/O 桥接和生命周期管理
- CLI 工具的智能来自工具本身（Claude Code、OpenCode 等），AgentHub 不重复造轮子去实现代码生成循环
- 接口契约是**约束**，不是负担——它保证模块之间不会因实现细节变化而断裂
- 目标架构图是**北星**，不是蓝图——每次增量向它靠近，但允许中间态简化
- Layer 可以暂时合并（Phase 1 的 API 和 Service 合在一起），但不能反向依赖（Service 绝不能依赖 API）
- Workspace 是 CLI Agent 的物理执行边界：所有 Agent 进程的 `cwd` 必须指向会话绑定的 `workspace_path`，路径访问必须校验在允许范围内
- P1（桌面版）使用 LocalWorkspaceProvider 操作本机文件系统，P2（SaaS 版）使用 CloudWorkspaceProvider 操作云端沙箱

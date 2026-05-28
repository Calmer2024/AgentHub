# ADR-0008: Orchestrator 架构设计

**Date**: 2026-05-28
**Status**: Draft
**Replaces**: ADR-0005 §2 (Message Service Contract, partial), Phase 3 Spec §5.1

---

## 1. Context

### 1.1 问题

Phase 3 Spec §5.1 对 Orchestrator 的描述只有 3 段行为规格（L1/L2/L3），缺少：
- **架构设计**: 组件如何组合？数据如何流转？
- **接口契约**: 各组件之间的边界在哪里？
- **状态模型**: 并行/串行/链式三种执行模式如何切换？
- **错误处理**: Agent 超时、不可用、返回异常时如何降级？
- **可测试性**: 如何在无真实 Agent 的情况下测试编排逻辑？

当前实现 (`orchestrator_v2.py`) 是一个原型级别的 Pipeline，但缺乏完整的架构指导。

### 1.2 目标

设计一个**可渐进实现的** Orchestrator 架构，满足：
1. **清晰的分层和接口** — 每个组件可独立测试
2. **支持三种执行模式** — Single / Parallel / Chain
3. **可扩展的意图系统** — 当前用关键词规则，未来可升级为 LLM-based
4. **与 ContextManager/EventBus 的标准化集成**
5. **不破坏现有 SSE 事件协议** — 前端无需改动

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **Pipeline Pattern** | 请求经过多个不可变阶段，每阶段产生中间结果 |
| **纯 Domain 层** | Orchestrator 零 FastAPI/SQLAlchemy 依赖，通过接口与外部通信 |
| **意图驱动** | 用户消息 → 意图 → Agent 选择 → 执行计划 |
| **观察者模式** | EventBus 发布生命周期事件，订阅者（WS推送/持久化/产物检测）解耦 |
| **渐进增强** | L1 → L2 → L3 逐步实现，每层可独立测试和上线 |

---

## 3. 架构总览

```
                             ┌─────────────────────┐
                             │   ChatServiceImpl    │  (Service Layer)
                             │   thin coordinator   │
                             └──────────┬──────────┘
                                        │ PipelineRequest
                                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                       Orchestrator (Domain Layer)                  │
│                                                                    │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│  │ Stage 1      │   │ Stage 2      │   │ Stage 3               │  │
│  │ Context      │──▶│ Agent        │──▶│ Execution             │  │
│  │ Assembly     │   │ Selection    │   │ Planning              │  │
│  └──────┬───────┘   └──────┬───────┘   └───────────┬───────────┘  │
│         │                  │                       │              │
│         ▼                  ▼                       ▼              │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│  │ContextManager│   │IntentAnalyzer│   │  Mode Decision        │  │
│  │- token budget│   │- keyword L1  │   │  single? parallel?    │  │
│  │- pin priority│   │- LLM L2(fut) │   │  chain?               │  │
│  │- FIFO trunc  │   │AgentSelector │   │  TaskDecomposer       │  │
│  └──────────────┘   │- score matrix│   └───────────┬───────────┘  │
│                     └──────────────┘               │              │
│                                                    ▼              │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Stage 4: Lifecycle Events (EventBus)                        │ │
│  │ ORCHESTRATOR_TASK_STARTED → AGENT_CALL_STARTED →            │ │
│  │ AGENT_CALL_COMPLETED → ORCHESTRATOR_TASK_COMPLETED          │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  Output: PipelineResult { agent_calls, execution_mode, ... }       │
└───────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                    AgentExecutor (Service Layer)                   │
│                                                                    │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────┐             │
│  │ Single     │  │ Parallel     │  │ Chain         │             │
│  │ 1 agent    │  │ N agents     │  │ A output → B  │             │
│  │ direct     │  │ StreamMerger │  │ sequential    │             │
│  └────────────┘  └──────────────┘  └───────────────┘             │
└───────────────────────────────────────────────────────────────────┘
```

---

## 4. 组件详细设计

### 4.1 IntentAnalyzer (意图分析器)

**职责**: 从用户消息中提取意图类型。

**当前实现**: 关键词规则匹配（`INTENT_KEYWORDS` 表）

```python
class IntentAnalyzer:
    """意图分析器接口。当前为规则匹配，未来可替换为 LLM-based。"""

    def analyze(self, content: str) -> Intent:
        """返回意图类型 + 置信度"""
        ...

@dataclass
class Intent:
    type: str           # "code_gen" | "research" | "design_ui" | "general_qa"
    confidence: float   # 0.0 - 1.0
    evidence: str       # 匹配到的关键词，用于调试
```

**演进路径**:
- Phase 3 (当前): 关键词规则 → `confidence = 1.0 if matched else 0.3`
- Phase 4 (升级): 用轻量 LLM (如 DeepSeek Flash) 做意图分类 → JSON 输出

### 4.2 AgentSelector (Agent 选择器)

**职责**: 根据意图从候选 Agent 中选择最佳匹配。

**当前实现**: Provider × Intent 评分矩阵（`AGENT_INTENT_SCORES`）

```python
class AgentSelector:
    """Agent 选择器。"""

    def select(self, intent: Intent, candidates: list[AgentConfig],
               mentions: list[str] | None = None) -> list[ScoredAgent]:
        """返回按得分排序的 Agent 列表"""
        ...

@dataclass
class ScoredAgent:
    agent: AgentConfig
    score: int
    reason: str  # "exact_mention" | "intent_match" | "fallback"
```

**选择策略优先级**:
1. `@mention` → 精确匹配，得分 ∞（最高优先）
2. 意图匹配 → 评分矩阵排序
3. Fallback → 返回全部（得分相同）

### 4.3 TaskDecomposer (任务拆解器)

**职责**: 将复杂请求拆解为子任务，匹配到合适 Agent。

```python
class TaskDecomposer:
    """L2: 复杂请求拆解。"""

    def is_complex(self, content: str) -> bool:
        """判断是否需要拆解"""
        ...

    def decompose(self, intent: Intent, agents: list[ScoredAgent]
                  ) -> list[SubTask]:
        """按模板拆解，返回子任务→Agent 映射"""
        ...

@dataclass
class SubTask:
    name: str           # "frontend" | "backend" | "search" | "summary"
    description: str    # 注入 prompt 的任务描述
    agent: AgentConfig
    tags: list[str]     # 用于匹配 Agent 的标签
```

**拆解模板** (可扩展):
```python
TASK_TEMPLATES = {
    "code_gen": [
        SubTask("frontend", "实现前端界面和交互逻辑", tags=["React", "UI"]),
        SubTask("backend", "实现后端API和数据库", tags=["Python", "API"]),
    ],
    "research": [
        SubTask("search", "搜索相关资料和数据", tags=["search", "analysis"]),
        SubTask("summary", "总结分析结果", tags=["writing", "summary"]),
    ],
}
```

### 4.4 ExecutionPlanner (执行计划器)

**职责**: 根据选中 Agent 和复杂度决定执行模式。

```python
class ExecutionPlanner:
    """Stage 3: 决定执行模式并构建 AgentCall 列表。"""

    def plan(self, agents: list[ScoredAgent], content: str,
             messages: list[dict], decomposer: TaskDecomposer
             ) -> ExecutionPlan:
        ...

@dataclass
class ExecutionPlan:
    mode: str           # "single" | "parallel" | "chain"
    calls: list[AgentCall]
    system_prompt_override: str | None  # 链式协作时，后续 Agent 的特殊 prompt
```

**决策逻辑**:
```
agents.count == 0 → mode=empty, calls=[]
agents.count == 1 → mode=single
is_complex(content) AND agents >= 2
  → decompose → mode=parallel (with task assignment)
agents >= 2 AND !is_complex
  → mode=parallel (all with "primary" task)
chain_config exists → mode=chain (sequential, each has previous output)
```

### 4.5 ContextManager (上下文管理器)

**集成点**: Pipeline Stage 1 调用。Module 1 中已实现核心逻辑，Module 4 负责集成。

```python
# 在 Pipeline 中的调用位置:
class Orchestrator:
    def __init__(self, context_manager: ContextManager, ...):
        self.ctx = context_manager

    async def run(self, req: PipelineRequest) -> PipelineResult:
        # Stage 1
        ctx_output = self.ctx.assemble(PromptAssemblyInput(
            session_id=req.session_id,
            system_prompt=req.system_prompt,
            messages=req.messages,
            pinned_message_ids=req.pinned_message_ids,
            max_tokens=req.context_budget,
            reserve_tokens=req.reserve_tokens,
        ))

        if ctx_output.truncated:
            logger.warning("Context truncated: %d tokens", ctx_output.total_tokens)
```

---

## 5. 执行模式状态机

```
                    ┌──────────┐
                    │  Start   │
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐ ┌────────┐ ┌────────┐
         │ single │ │parallel│ │ chain  │
         └───┬────┘ └───┬────┘ └───┬────┘
             │          │          │
             │     ┌────▼────┐     │
             │     │decompose│     │
             │     │ N tasks │     │
             │     └────┬────┘     │
             │          │          │
             ▼          ▼          ▼
         ┌─────────────────────────────┐
         │     AgentExecutor.execute() │
         │  ┌──────┐ ┌──────┐ ┌─────┐ │
         │  │direct│ │gather│ │seq  │ │
         │  └──┬───┘ └──┬───┘ └──┬──┘ │
         └─────┼─────────┼─────────┼───┘
               ▼         ▼         ▼
         ┌─────────────────────────────┐
         │   TokenEvent Stream (SSE)   │
         └─────────────────────────────┘
```

### 各模式行为:

**Single**: 1 个 Agent 直接调用 → 逐 token SSE 输出
**Parallel**: N 个 Agent → `StreamMerger.merge()` 交错输出 → 前端按 `agentId` 分别渲染
**Chain**: A → B → C → 每步完成后，输出作为下步的额外 context → 前端显示折叠卡片

---

## 6. SSE 事件协议

保持与现有前端兼容，不引入 breaking changes。

```json
// 路由决策（群聊）
{"type": "orchestrator.route", "agents": [{"id": "..", "name": "Claude"}]}

// Agent 开始（每个 Agent 一条）
{"type": "agent.start", "agentId": "..", "agentName": "Claude", "messageId": ".."}

// Token 流
{"token": "...", "agentId": "..", "agentName": "Claude", "done": false}

// Agent 完成（每个 Agent 一条）
{"token": "", "agentId": "..", "agentName": "Claude", "done": true, "messageId": ".."}

// === Phase 3 新增（可选，前端当前忽略） ===
// 任务开始
{"type": "orchestrator.task_started", "intent": "code_gen", "tasks": ["frontend", "backend"]}

// 任务完成
{"type": "orchestrator.task_completed", "summary": "2 agents completed"}
```

---

## 7. 错误处理矩阵

| 场景 | 行为 | 用户看到 |
|------|------|---------|
| 单个 Agent 不可用 | `[Agent名 不可用]` 占位消息 | 红色错误气泡 |
| 单个 Agent 超时 (60s) | `asyncio.wait_for` → `[Agent名 响应超时]` | 黄色警告气泡 |
| 单个 Agent 返回异常 | catch Exception → `[Agent名 错误: {msg}]` | 红色错误气泡 |
| 并行中部分 Agent 失败 | 成功的不受影响，失败的显示错误 | 部分正常+部分错误 |
| 所有 Agent 都失败 | 返回 "所有 Agent 均无法响应" | 全局错误横幅 |
| EventBus 发布失败 | 静默 catch，记录日志 | 无影响（fire-and-forget） |
| ContextManager 截断 | `result.truncated = True`, 日志记录 | 透明（消息可能丢失旧上下文） |
| 链式中间步骤失败 | 链中断，返回已完成步骤结果 + 错误 | 显示 "链式协作在步骤 N 中断" |

---

## 8. 测试策略

### 单元测试 (Domain 层纯逻辑，无需真实 Agent)

```python
# test_orchestrator_v2.py — 20 条 (已完成)
class TestPipeline:
    - Stage 1: ContextManager 截断
    - Stage 2: @mention 精确 / 意图匹配 / 空 Agent
    - Stage 3: complex 拆解 / simple 不拆解 / chain 模式
    - Stage 4: EventBus 事件发布

# test_intent_analyzer.py — 新增
class TestIntentAnalyzer:
    - 每条关键词至少 1 条匹配测试
    - 中文/英文混合
    - 边界: 空字符串、纯符号
```

### 集成测试 (Mock Agent)

```python
# test_agent_executor.py — 新增
class TestAgentExecutor:
    - single: 正常流式 + 异常
    - parallel: 2-5 个并发, 交错顺序验证
    - chain: A→B 顺序, B 收到 A 的输出
```

### E2E 测试 (Playwright)

```python
# e2e/orchestrator/test_group_chat.py
- 未 @ → 意图驱动选择 Agent
- @指定 → 精确路由
- 复杂请求 → 拆解 + 并行执行
- 链式配置 → A 产出 → B 审查
```

---

## 9. 渐进实现路径

### Phase 3 Module 4 (当前目标)

**Week 1: Pipeline 完善**
- [ ] IntentAnalyzer 接口抽象（当前为关键词，定义 ABC 为未来 LLM 预留）
- [ ] AgentSelector 从 orchestrator_v2 中独立
- [ ] ExecutionPlanner 明确三种模式决策逻辑
- [ ] ContextManager 集成到 Stage 1

**Week 2: AgentExecutor 完善**
- [ ] single 模式：错误处理完善
- [ ] parallel 模式：StreamMerger + 部分失败处理
- [ ] chain 模式：上一步输出注入 prompt + 截断保护
- [ ] EventBus 生命周期事件完整覆盖

**Week 3: 测试 + 前端**
- [ ] 30+ 条单元/集成测试
- [ ] CollabProgressCard 完成态更新
- [ ] Orchestrator 进度横幅增强
- [ ] 全量回归 + E2E 验证

### Future: Phase 4+ 演进

- **LLM-based Intent**: 用 DeepSeek Flash 做意图分类，替代关键词规则
- **Dynamic Replanning (L4)**: Agent 失败时自动切换到备选 Agent
- **History Compression**: ContextManager 使用 LLM 自动摘要替代 FIFO 截断

---

## 10. 关键决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| Pipeline 模式 | Pipeline vs. Chain of Responsibility vs. Strategy | **Pipeline** | 每阶段不可变，易于测试和调试 |
| 意图识别 | 关键词 vs. LLM 分类 | **关键词 (Phase 3)** | 零延迟、零成本，Phase 4 升级为 LLM |
| Agent 选择 | 评分矩阵 vs. LLM 推荐 | **评分矩阵** | 可控、可调试、确定性 |
| 并行上限 | 3 vs. 5 vs. 无限 | **5** | 平衡并发成本和响应速度 |
| 链式中间展示 | 完整展示 vs. 折叠摘要 vs. 隐藏 | **折叠摘要** | 不打断用户，但可展开审查 |
| 执行器位置 | Domain 层 vs. Service 层 | **Service 层** | Agent 调用涉及 I/O，应在 Service 层 |

---

## 11. 接口契约汇总

```python
# === Pipeline 输入 ===
@dataclass
class PipelineRequest:
    session_id: str
    content: str
    mentions: list[str] | None
    messages: list[dict]
    member_agents: list[AgentConfig]
    system_prompt: str = ""
    pinned_message_ids: list[str] = field(default_factory=list)
    context_budget: int = 100_000
    reserve_tokens: int = 4096
    chain_config: ChainConfig | None = None  # Phase 3 L3

# === Pipeline 输出 ===
@dataclass
class PipelineResult:
    agent_calls: list[AgentCall]
    execution_mode: str  # "single" | "parallel" | "chain"
    assembled_messages: list[dict]
    total_tokens: int
    truncated: bool
    intent: str = "general_qa"

# === Agent 调用单元 ===
@dataclass
class AgentCall:
    agent: AgentConfig
    task: str = "primary"
    input_messages: list[dict] = field(default_factory=list)

# === Executor 输出 ===
class TokenEvent:
    agent_id: str
    agent_name: str
    token: str
    done: bool
    message_id: str
    error: str
```

---

## 12. 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-28 | v1.0 | 初始架构设计: Pipeline 四阶段, 三种执行模式, SSE 协议, 错误处理矩阵 |

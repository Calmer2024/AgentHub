# ADR-0007: Orchestrator 架构设计

**Date**: 2026-05-28
**Status**: Accepted (finalized 2026-06-01)
**Replaces**: ADR-0005 §2 (Message Service Contract, partial), Phase 3 Spec §5.1

> **2026-06-04 修订说明**：本 ADR 记录 Phase 3 Orchestrator 设计时的历史语境，其中“Agent 底层调用多家 HTTP 模型厂商”“orchestratorProvider/orchestratorModel”等表述已被 [ADR-0009](0009-project-workspace-model.md) 和 [PRD-01](../PRD/01-Architecture_Adapter.md) 覆盖。当前产品口径是：用户可见 Agent 只代表本机 CLI 工具实例；DeepSeek 只作为后端内部系统模型能力，用于标题生成、中枢总结和产物编辑辅助。

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

**职责**: 根据意图和能力需求，从候选 Agent 中选择最佳匹配。

**核心概念**: **Agent ≠ Provider**。Agent 是用户创建的自定义实体（名称、描述、system_prompt 均可自定义），底层调用 4 家厂商模型（DeepSeek/Gemini/GLM/MiniMax）。多个 Agent 可能使用同一家模型，但能力标签不同。

**当前实现**: 基于 Agent 元数据（`description` + `system_prompt`）与任务需求标签匹配

```python
class AgentSelector:
    """Agent 选择器。匹配依据: Agent.description + Agent.system_prompt。"""

    def select(self, intent: Intent, required_tags: list[str],
               candidates: list[AgentConfig],
               mentions: list[str] | None = None) -> list[ScoredAgent]:
        """返回按得分排序的 Agent 列表"""
        ...

@dataclass
class ScoredAgent:
    agent: AgentConfig
    score: int
    match_tags: list[str]  # 匹配到的能力标签
    reason: str  # "exact_mention" | "tag_match" | "description_match" | "fallback"
```

**选择策略优先级**:
1. `@mention` → 精确匹配 Agent 名称（用户自定义名称），得分 ∞（最高优先）
2. 能力标签匹配 → `required_tags` 与 Agent 的 `system_prompt` + `description` 做关键词匹配
3. Fallback → 返回全部（得分相同）

### 4.3 TaskDecomposer (任务拆解器)

**职责**: 将复杂请求拆解为子任务，为每个子任务分配**角色**和匹配 Agent。

```python
class TaskDecomposer:
    """L2: 复杂请求拆解 + 动态角色分配。"""

    def is_complex(self, content: str) -> bool:
        """判断是否需要拆解"""
        ...

    def decompose(self, intent: Intent, agents: list[ScoredAgent]
                  ) -> list[SubTask]:
        """按模板拆解，动态分配角色 → Agent 映射"""
        ...

@dataclass
class SubTask:
    name: str           # "planning" | "frontend" | "backend" | "review"
    role: str           # 动态角色: "planner" | "executor" | "reviewer" | "researcher" | "synthesizer" | "critic"
    description: str    # 注入 prompt 的任务描述
    agent: AgentConfig
    tags: list[str]     # 用于匹配 Agent 能力的标签
```

**拆解模板** (Phase 3 模板驱动，Phase 4 升级 LLM 动态):

```python
TASK_TEMPLATES = {
    "code_gen": [
        SubTask("planning", role="planner", "制定技术方案和架构设计", tags=["架构", "设计"]),
        SubTask("implementation", role="executor", "按方案实现代码", tags=["开发", "代码"]),
        SubTask("review", role="reviewer", "审查代码质量和安全性", tags=["审查", "测试"]),
    ],
    "research": [
        SubTask("search", role="researcher", "搜索相关资料和数据", tags=["搜索", "分析"]),
        SubTask("synthesize", role="synthesizer", "综合信息形成结论", tags=["写作", "总结"]),
        SubTask("critique", role="critic", "提出反对意见和遗漏点", tags=["批判", "检查"]),
    ],
}
```

**角色定义** (Phase 3 模板枚举):

| 角色 | 职责 | 典型 Prompt 注入 |
|------|------|-----------------|
| `planner` | 分析需求，制定方案 | "你需要制定详细的技术方案，不写具体代码" |
| `executor` | 按方案产出具体内容 | "按照上一步的方案，产出具体实现" |
| `reviewer` | 审查产出质量 | "审查以上产出，指出问题和改进建议" |
| `researcher` | 收集信息 | "搜索和收集相关信息，整理为结构化材料" |
| `synthesizer` | 综合多源信息 | "综合以上信息，形成最终结论" |
| `critic` | 质疑和补充 | "找出方案的漏洞、遗漏和风险点" |

### 4.4 ExecutionPlanner (执行计划器)

**职责**: 根据选中 Agent 和任务复杂度决定执行模式和角色分配。

**关键原则 (自动化优先)**: 链式协作**自动触发**，不需要用户手动配置开关。用户只需描述任务，Orchestrator 自动判断是否需要多阶段协作。

```python
class ExecutionPlanner:
    """Stage 3: 决定执行模式并构建 AgentCall 列表。"""

    def plan(self, agents: list[ScoredAgent], content: str,
             messages: list[dict], decomposer: TaskDecomposer
             ) -> ExecutionPlan:
        ...
```

**决策逻辑** (按优先级):
```
agents.count == 0                       → mode=empty, calls=[]
agents.count == 1                       → mode=single
is_complex(content) AND agents >= 2     → mode=chain (自动链式，角色模板分配)
is_complex(content) AND agents >= 2 AND task_phases > 2
                                        → mode=parallel (同级子任务并行)
agents >= 2 AND !is_complex              → mode=parallel (all "primary" 角色)
```

**自动链式触发条件** (无需用户配置):
- 检测到多阶段关键词 ("先...再..."、"然后"、"最后")
- 任务有明确阶段性依赖 (模板匹配)
- Agent 之间存在能力互补 (不同标签覆盖不同子任务)

```python
@dataclass
class ExecutionPlan:
    mode: str           # "single" | "parallel" | "chain"
    calls: list[AgentCall]
    chain_roles: list[str]  # 链式模式下每步的角色名
    system_prompt_override: str | None  # 角色 Prompt 注入
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
         │1 agent │ │N agents│ │A→B→C   │
         │direct  │ │concurr.│ │staged  │
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
         └─────────────┬───────────────┘
                       ▼
         ┌─────────────────────────────┐
         │   TokenEvent Stream (SSE)   │
         └─────────────┬───────────────┘
                       ▼
         ┌─────────────────────────────┐
         │  CollaborationView (前端)    │
         │  独立协作面板，非多气泡       │
         └─────────────────────────────┘
```

### 各模式行为:

**Single**: 1 个 Agent 直接调用 → 逐 token SSE 输出 → 直接渲染聊天气泡
**Parallel**: N 个 Agent → `StreamMerger.merge()` 交错输出 → **CollaborationView 独立协作面板** → 各 Agent 思考/计划/工具调用独立展示 → 最终合成一个结果气泡
**Chain**: A(规划) → B(执行) → C(审查) → 每步完成后注入下步 → **CollaborationView 展示链式步骤** → 最终统一输出

### 前端渲染模式 (v2)

不再渲染多个独立聊天气泡，改为：

```
ChatWindow
├── 用户消息气泡 (正常)
├── CollaborationView (多 Agent 协作专用面板)
│   ├── Agent A 卡片: 思考过程 + 工具调用 + 计划内容 + 状态
│   ├── Agent B 卡片: 思考过程 + 工具调用 + 执行内容 + 状态
│   ├── Agent C 卡片: 审查内容 + 状态
│   └── 最终合成结果: 统一的聊天气泡
└── 后续对话...
```

`CollaborationView` 是独立 UI 组件，替换当前的并行多气泡模式。

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

### Phase 3 Module 4 (已完成)

**Week 1: Pipeline 完善**
- [x] IntentAnalyzer 独立组件（当前为关键词规则；按最终决议暂不定义 ABC）
- [x] AgentSelector 从 orchestrator_v2 中独立
- [x] ExecutionPlanner 明确模式决策逻辑，并支持 DAG Phase 分配
- [x] ContextManager 集成到 Stage 1

**Week 2: AgentExecutor 完善**
- [x] single 模式：错误处理完善
- [x] parallel 模式：StreamMerger + 部分失败处理
- [x] chain 模式：上一步输出注入 prompt + 截断保护
- [x] dag 模式：SharedContext + Phase 间串行/Phase 内并行
- [x] EventBus 生命周期事件覆盖成功和失败路径

**Week 3: 测试 + 前端**
- [x] 30+ 条单元/集成测试
- [x] CollaborationPanel 替代 CollabProgressCard
- [x] Orchestrator 进度横幅增强
- [x] 全量回归 + 真实 API/UI/Mobile 验证

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
| Agent 选择 | Provider评分 vs. Agent元数据匹配 | **Agent元数据匹配** | Agent≠Provider；用户自定义名称/描述/system_prompt，元数据匹配更精准 |
| 并行上限 | 3 vs. 5 vs. 无限 | **5** | 平衡并发成本和响应速度 |
| 链式触发方式 | 手动开关 vs. 自动判断 | **自动判断** | 自动化优先原则；Phase 3 模板驱动 + Phase 4 LLM 动态 |
| 角色分配 | 硬编码 producer/reviewer vs. 模板枚举 vs. LLM动态 | **模板枚举 (Phase 3)** | 6 种角色模板覆盖常见场景，Phase 4 升级 LLM 动态 |
| 协作展示 | 多气泡 vs. 协作面板 vs. 折叠卡片 | **面板 + Agent气泡 + 中枢总结** | 保留每个 Agent 的可追溯产出；DAG/chain 等结构化协作由 Orchestrator 汇总成最终答复 |
| 执行器位置 | Domain 层 vs. Service 层 | **Service 层** | Agent 调用涉及 I/O，应在 Service 层 |
| 自动化程度 | 用户配置 vs. 自动处理 | **自动化优先** | 复杂决策由后端 Orchestrator 自动完成，不暴露给用户 |
| 消息来源建模 | agentName 字符串 vs. 一等来源字段 | **sourceType/contentType/metadata** | 支持系统整理、产物归属、审计和后续重新综合 |
| Orchestrator 模型 | 借用成员 Agent vs. 独立配置 | **独立 orchestratorProvider/orchestratorModel** | 中枢是编排层能力，不应受某个成员 Agent 的模型身份影响 |
| 调度器第一版形态 | 自动执行 vs. Plan-first dry-run | **只生成 draft plan** | 先可视化和调试调度脑子，避免过早唤醒真实 Agent |
| 调度器 Agent | 硬编码服务 vs. Engine + Toolset Agent | **特殊 Agent Profile** | 与 Agent = Engine + Toolset + Context Policy 的产品模型保持一致 |
| 任务分配口径 | 只按 Agent vs. 只按 Skill vs. 二者同时保留 | **required_skills + assigned_agent_id + reason** | 执行按 Agent，解释和兜底按能力 |
| 第一版 Engine | ClaudeCode CLI vs. LLM 假 Agent | **LLM 假 Agent** | 真实 CLI 接入前先跑通结构化计划链路 |

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

## 12. Final Design Decisions (2026-06-01 Grill Session)

以下决议在 grill-with-docs 会话中确认，作为架构实现的最终依据。

### 核心理念纠正

| 旧理解 | 新理解 |
|--------|--------|
| Agent = Provider (Claude/DeepSeek 等) | Agent 是用户自定义实体（名称、描述、system_prompt），底层调用 4 家厂商模型 (DeepSeek/Gemini/GLM/MiniMax) |
| 评分按 provider 名字 | 评分按 Agent 的 description + system_prompt 标签匹配 |
| 链式由用户手动开关 | Orchestrator 自动判断触发 + 动态分配角色 |
| 并行 = 多个聊天气泡 | 独立 CollaborationView 协作面板 → 合成一个结果气泡 |
| 角色 = producer/reviewer | 6 种模板角色: planner/executor/reviewer/researcher/synthesizer/critic |

### 架构决议

| # | 决议 | 选择 | 理由 |
|---|------|------|------|
| 1 | 组件拆分粒度 | **独立类，暂不定义 ABC** | 各组件当前只有一个实现，ABC 是 YAGNI；但独立类=可独立测试+Phase 4 可替换 |
| 2 | 链式触发方式 | **Orchestrator 自动判断** | 自动化优先；Phase 3 模板驱动，Phase 4 LLM 动态 |
| 3 | 角色分配 | **6 种模板枚举，动态匹配** | 覆盖常见场景；不硬编码 producer/reviewer |
| 4 | V1 去留 | **删除 orchestrator.py** | V2 覆盖全部功能 |
| 5 | 执行模式优先级 | **自动链式 > complex(chain) > parallel > single** | 多阶段依赖自动串联 |
| 6 | SSE 新增事件 | **task_started + chain_step + task_completed** | 为 CollaborationView 提供结构化数据 |
| 7 | 错误处理补齐 | **超时 60s + 全失败兜底 + 链中断处理** | 补齐 3 项保护缺口 |
| 8 | 前端协作展示 | **CollaborationView 独立面板** | 每个Agent思考/计划/工具调用独立展示，最终统一结果气泡 |
| 9 | 开发规则 | **自动化优先原则** | 任何功能设计让任务尽量自动化，不暴露过多配置给用户 |

### 6 种动态角色

| 角色 | 职责 | 典型 Prompt 注入 |
|------|------|-----------------|
| `planner` | 分析需求，制定方案 | "制定详细的技术方案，不写具体代码" |
| `executor` | 按方案产出内容 | "按照上一步方案，产出具体实现" |
| `reviewer` | 审查产出质量 | "审查以上产出，指出问题和改进建议" |
| `researcher` | 收集信息 | "搜索和收集相关信息，整理为结构化材料" |
| `synthesizer` | 综合多源信息 | "综合以上信息，形成最终结论" |
| `critic` | 质疑和补充 | "找出方案漏洞、遗漏和风险点" |

### 开发步骤概要

| Step | 名称 | 产出 |
|------|------|------|
| 1 | 领域层重构 | IntentAnalyzer(Agent元数据匹配), AgentSelector(标签匹配), TaskDecomposer(6角色模板), ExecutionPlanner(自动链式决策), 删除V1 |
| 2 | 执行层完善 | TokenEvent 扩展(thinking/planning/tool_call), 超时/全失败/链中断, 3种新SSE事件 |
| 3 | API层贯通 | chainConfig 运行时参数, PipelineRequest 透传, 链式 SSE 序列化 |
| 4 | 前端全链路 | CollaborationView 独立面板, SSE 事件驱动, CollabProgressCard(思考/计划/工具), ChatWindow 增强 |
| 5 | 测试+文档+收尾 | 独立组件单测, Executor 集成, E2E, 全量回归 |

## 13. Plan-first 调度器收敛决策 (2026-06-04)

本节记录 2026-06-04 需求对齐后的 Orchestrator 优化方向。该方向不推翻 Phase 3 已完成的 Pipeline/DAG/CollaborationPanel 基础设施，而是将调度入口收敛为“先产出可解释计划，再进入执行”的 Plan-first 模式。

### 13.1 Agent 与 Skill 模型

AgentHub 的 Agent 模型统一为：

```text
Agent = Engine + Toolset + Context Policy
```

- `Engine` 可以是 LLM API、ClaudeCode CLI、Codex CLI 等。
- `Toolset` 是 Agent 可用能力集合。用户自定义 Agent 不再区分主能力与辅助能力；本机 Skill 只作为可选工具集来源。
- `Context Policy` 决定执行时如何注入 Project、Session、Pin、Reply、Artifact 等上下文。
- Orchestrator 也是一个特殊 Agent，使用内置 System Prompt、Rules、Toolset 与 Engine 配置。

运行时由 Prompt Assembly 把 Agent 的身份提示、规则、工具集摘要、本机 Skill 内容和任务上下文一起组装。第一版只要求 Orchestrator 能看见 Agent Profile 快照并据此分配任务，不实现完整执行 Prompt Assembly。

### 13.2 第一版边界

第一版只实现：

```text
用户输入 -> LLM 假 Orchestrator -> draft plan JSON -> 后端 parse/validate/normalize -> 前端调试台可视化
```

明确不做：

- 自动执行子 Agent。
- Plan 修订交互。
- 真实 ClaudeCode/Codex CLI 调用。
- 完整执行 Prompt Assembly。
- 资源感知、Git 分支、文件锁、复杂 DAG 编辑器。
- 风险矩阵、能力缺口分析等高级规划字段。

### 13.3 Plan 最小契约

顶层字段：

```json
{
  "plan_id": "plan_001",
  "status": "draft",
  "execution_policy": "manual_approval_required",
  "tasks": [],
  "execution_strategy": {
    "summary": "先需求和契约，再并行实现，最后验收。",
    "phases": []
  }
}
```

每个任务字段：

```json
{
  "task_id": "T1",
  "title": "架构设计与接口契约",
  "goal": "明确系统模块、API 契约和数据模型",
  "required_skills": ["architecture", "api_design"],
  "assigned_agent_id": "mock_architect",
  "assigned_agent_name": "架构专家",
  "assignment_reason": "匹配 architecture 主 skill",
  "depends_on": [],
  "expected_outputs": ["document"],
  "acceptance_criteria": ["产出 API 契约", "产出数据模型"],
  "needs_approval": true,
  "is_blocking": true
}
```

任务拆分粒度为模块/交付物级，不拆到“创建文件、安装依赖、写函数”这类代码步骤级。执行 Agent 后续自行决定技术动作。

### 13.4 调试台输出

dry-run API 至少返回：

- `input`：用户原始输入。
- `orchestrator_agent`：本次调度器 Agent Profile。
- `candidate_agents`：可调度 Agent 快照。
- `raw_output`：LLM 原始输出。
- `normalized_plan`：后端规范化后的计划。
- `validation`：结构校验结果。

Validator 第一版强校验 DAG 结构：`task_id` 唯一、`depends_on` 引用存在、无循环依赖、至少有起点任务。内容质量问题先记录 warning，不阻断 dry-run。

---

## 14. 最终用户交互设计 (2026-06-01 Grill Part 2)

> 详细规格见 **[docs/archive/phases/specs/phase3/02-orchestrator/](../archive/phases/specs/phase3/02-orchestrator/README.md)**。本节省略实现细节，仅记录架构决策。

### 14.1 核心理念纠正

当前实现：Orchestrator 分发给 N 个 Agent → 各自独立回复 → 互不知晓。**这是多路复用，不是协作。**

最终目标：多个 Agent 像群聊成员一样依次回复各自的产出，可以**并行完成不同任务**，也可以**串行完成有依赖的任务**，全程由 Orchestrator 调度。

### 14.2 最终架构决议

| # | 决议 | 选择 |
|---|------|------|
| 1 | 协作形态 | **混合 DAG 模式** — 同一请求内 Phase 间串行、Phase 内并行 |
| 2 | 上下文共享 | **对话流共享 + 定向注入** — 所有 Agent 可见的共享对话历史，链式依赖的前驱产出定向注入 |
| 3 | 前端渲染 | **面板 + 气泡混合** — CollaborationPanel (DAG 俯瞰) + Agent 聊天气泡 (协作对话感) |
| 4 | 并行气泡 | **同时流式 + 角色排序** — 同一 Phase 的 Agent 气泡同时出现，独立流式，完成后按角色优先级排列 |
| 5 | 调度策略 | **DAG 依赖拓扑** — SubTask.depends_on 声明依赖，ExecutionPlanner 分配 Phase，AgentExecutor._execute_dag() 按拓扑执行 |
| 6 | SSE 协议 | **task_started v2 (含 phases DAG) + phase_change 事件** |
| 7 | 最终答复 | **Orchestrator 中枢总结** — DAG/chain 且至少 2 个 Agent 成功产出后，由独立 Orchestrator 模型配置生成一条系统整理消息 |

### 14.3 协作体验示意

```
用户: "帮我做登录系统，先设计方案再前后端实现，最后审查"

时间线:
  0.0s  Orchestrator 横幅 + CollaborationPanel 出现
       Panel: Phase 0(规划者)→Phase 1(前端∥后端)→Phase 2(审查者)

  Phase 0 (串行)
  2.0s  @架构师 [规划者] 气泡出现, 流式 "我来分析需求制定方案..."
  8.0s  @架构师 完成 ✅

  Phase 1 (并行 — 两个气泡同时出现)
  8.5s  @前端专家 [执行者] 气泡出现, 流式 "收到方案, 实现前端..."
  8.5s  @后端架构师 [执行者] 气泡出现, 流式 "收到方案, 实现后端..."
  15s   @后端架构师 完成 ✅
  18s   @前端专家 完成 ✅

  Phase 2 (串行)
  18.5s @代码审查员 [审查者] 气泡出现, 流式 "审查结果: 前端缺少表单验证..."
  25s   @代码审查员 完成 ✅

  25s   Orchestrator 中枢总结气泡出现, 流式整合各 Agent 产出
  30s   协作完成, Panel 折叠, 最终答复显示
```

### 14.4 当前实现 vs 最终目标

| 维度 | 当前 (Phase 3.4/3.5 完成后) | 最终目标 (Phase 3.6) |
|------|---------------------------|---------------------|
| 协作形态 | 全并行 OR 全串行 | **混合 DAG** |
| 上下文共享 | 所有 Agent 相同 input | **共享上下文 + 定向注入** |
| SubTask 模型 | name + role + tags | **+ depends_on + phase** |
| ExecutionPlanner | ChainConfig / is_complex → mode | **depends_on → 拓扑排序 → Phase 分配** |
| AgentExecutor | single/parallel/chain | **+ _execute_dag** |
| SSE 事件 | task_started(tasks) + chain_step | **task_started(phases DAG) + phase_change** |
| 前端组件 | CollaborationView (面板) | **CollaborationPanel (DAG 图 + 进度)** |
| Agent 气泡 | 同时创建, 独立渲染 | **同时创建 + 角色标签 + Phase 分组** |
| 最终答复 | 无明确来源 | **结构化协作: 中枢总结气泡 + sourceType=orchestrator** |
| 协作感 | 无 — Agent 互不知晓 | **有 — 对话流共享 + 定向注入** |

---

## 15. 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-04 | v1.6 | Plan-first 调度器收敛: LLM 假 Agent、draft plan、最小 Plan 契约、dry-run 调试台输出 |
| 2026-06-01 | v1.5 | Grill Part 4: Orchestrator 中枢独立模型配置 |
| 2026-06-01 | v1.4 | Grill Part 3: 自动项目小队、中枢总结、消息来源一等建模 |
| 2026-06-01 | v1.3 | Grill Part 2: 混合 DAG、上下文共享、面板+气泡、phase_change 协议、最终交互设计 |
| 2026-06-01 | v1.2 | 5 Step 实现完成: 组件独立化、Agent 元数据匹配、6 角色模板、自动链式、CollaborationView、超时/中断/全失败 |
| 2026-06-01 | v1.1 | Grill 决议: 组件拆分, 链式运行时传递, V1 删除, 优先级链, 事件协议, 错误处理, 开发步骤 |
| 2026-05-28 | v1.0 | 初始架构设计: Pipeline 四阶段, 三种执行模式, SSE 协议, 错误处理矩阵 |

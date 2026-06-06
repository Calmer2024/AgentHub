# 04 — 执行引擎 (AgentExecutor)

**关联实现**: `backend/app/services/agent_executor.py`, `backend/app/infrastructure/stream_merger.py`

---

## 1. 概述

AgentExecutor 接收 AgentCall 列表 + 执行模式，调用真实 Agent 适配器，产出 TokenEvent 流。**不关心 SSE 格式或持久化** — 只产出结构化事件。

## 2. TokenEvent

### 2.1 数据模型

```python
class TokenEvent:
    agent_id: str       # 哪个 Agent 产生
    agent_name: str     # Agent 名称 (前端展示)
    token: str          # LLM token 文本
    done: bool          # Agent 是否已完成
    message_id: str     # 前端 message 标识
    error: str          # 错误信息 (Adapter 异常时填充)
    event_type: str     # "token" | "chain_step" | "phase_change" | ...
    metadata: dict      # 结构化元数据 (role, step, phase, status, ...)
```

### 2.2 事件类型枚举

| event_type | 用途 | metadata 示例 |
|-----------|------|--------------|
| `"token"` | 普通 LLM token | `{}` |
| `"chain_step"` | 链式步骤开始 | `{step, agent, role, total, status}` |
| `"phase_change"` | DAG Phase 切换 | `{phase, agents, status}` |

`is_chain_step` 和 `is_structured` 属性用于快速判别。

---

## 3. 执行模式

### 3.1 execute() 入口

```python
async def execute(calls, mode, dag_phases=None, shared_context=None):
    if mode == "dag":
        yield from _execute_dag(dag_phases, shared_context)
    elif mode == "chain":
        yield from _execute_chain(calls)
    elif mode == "parallel" and len(calls) > 1:
        yield from _execute_parallel(calls)
    else:
        yield from _execute_single(calls[0])
```

### 3.2 _execute_single — 单 Agent 调用

```
流程:
  1. EventBus: AGENT_CALL_STARTED
  2. 角色 Prompt 注入 (call.role_prompt_override → 追加到 system_prompt)
  3. CliAgentCallRunner → 对应 CLI adapter
  4. async for event in adapter.stream()
  5. 每个 token → TokenEvent(agent_id, agent_name, token)
  6. EventBus: AGENT_CALL_COMPLETED
  7. TokenEvent(done=True)

错误处理:
  · adapter 不存在 → TokenEvent(token="[Agent名 不可用]", error="adapter not found")
  · TimeoutError → TokenEvent(token="[Agent名 响应超时]", error="timeout")
  · Exception → TokenEvent(token="[Agent名 错误: {msg}]", error=str(e))
```

**关键实现细节**:
- 超时使用 `async with asyncio.timeout(60):` — 不是 `asyncio.wait_for`。`wait_for` 只接受 coroutine，不接受 async generator。
- 角色 Prompt 注入: 原始 system_prompt + `\n\n[角色: executor]\n实现具体代码`

### 3.3 _execute_parallel — 多 Agent 并行

```
流程:
  1. 为每个 AgentCall 创建 _execute_single 生成器 (最多 5 个)
  2. StreamMerger.merge(generators) → 按到达顺序交错产出 TokenEvent
  3. 各 Agent 异常隔离: 单个 Agent 失败不影响其他

并行限制: 5 个 (硬编码), 在 _execute_parallel 和 ExecutionPlanner 两处都做了截断
```

### 3.4 _execute_chain — 链式调用

```
流程:
  for i, call in enumerate(calls):
    1. 发送 chain_step TokenEvent (event_type="chain_step")
    2. 如果是第 i>0 步: 前一步产出注入到 call.input_messages
    3. _execute_single(call) → 逐 token 产出
    4. 检测步骤失败: ev.error 非空 → 发送 interrupted chain_step + break
    5. 前一步产出 → previous_output (供下一步注入)

中断检测:
  · 不是靠异常传播 (_execute_single 内部已 catch 所有异常)
  · 而是在 async for 循环结束后检查最后事件的 ev.error 字段
  · step_error 非空 → 发送 chain_step(status="interrupted") + break
```

### 3.5 _execute_dag — DAG 混合执行

目标行为:

```
for phase in phases:
    emit phase_change(phase, "running")
    if phase.mode == "parallel":
        # Phase 内所有 task 同时执行 (共享上下文 + 定向注入)
        yield from _execute_parallel_phase(phase, shared_context)
    else:
        # Phase 内单 task 串行
        yield from _execute_single(task)
        shared_context.append_output(task)
    emit phase_change(phase, "completed")
emit task_completed(phases_completed)
```

---

## 4. 流合并器 (StreamMerger)

用于并行模式下的 token 交错输出。

```
输入: [generator_A, generator_B, generator_C]
机制: asyncio.Queue + 并发消费
输出: 按 token 到达顺序交错 (A-A-B-A-C-B-B-A-...)

特性:
  · 异常隔离 (单个 gen 失败不影响其他)
  · 无背压 (Phase 3 规模: 5 agents × ~10K tokens < 1MB)
```

---

## 5. 错误处理矩阵

| 场景 | 触发条件 | 用户看到 | 实现位置 |
|------|---------|---------|---------|
| Agent 不可用 | CLI executable 缺失或会话无 Project workspace | 红色气泡 `[Agent名 不可用]` | `_execute_single` |
| 超时 60s | `asyncio.timeout` 触发 TimeoutError | 黄色气泡 `[Agent名 响应超时]` | `_execute_single` L127-146 |
| Agent 异常 | `adapter.chat_stream()` 抛异常 | 红色气泡 `[Agent名 错误: {msg}]` | `_execute_single` L148-155 |
| 并行部分失败 | 并行中个别 Agent 失败 | 成功的不受影响 | `_execute_single` 异常隔离 |
| 全失败 | 所有 agent_texts 为空 | 全局错误 "所有 Agent 均无法响应" | `chat_service_impl` L268-282 |
| 链中断 | 链中某步 `ev.error` 非空 | `chain_step(status="interrupted")` + 保留已完成步骤 | `_execute_chain` L209-232 |
| EventBus 失败 | publish 异常 | 静默 catch，无影响 | `_emit` try/except |
| Context 截断 | ctx.assemble() 返回 truncated | 透明（日志记录） | `orchestrator_v2` L138-154 |

---

## 6. 当前实现状态

| 功能 | 状态 | 备注 |
|------|------|------|
| _execute_single | ✅ | 60s 超时, 角色注入, 错误捕获 |
| _execute_parallel | ✅ | StreamMerger, 5 并发上限 |
| _execute_chain | ✅ | 产出注入, 中断检测 |
| _execute_dag | ✅ | 混合 DAG 执行器 |
| StreamMerger | ✅ | 交错合并, 异常隔离 |
| TokenEvent | ✅ | event_type + metadata |
| 错误处理矩阵 (8 场景) | ✅ | 全覆盖 |

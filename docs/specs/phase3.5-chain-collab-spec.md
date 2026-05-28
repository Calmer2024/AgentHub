# Spec: Phase 3.5 — 链式协作

**版本**: v1.0 | **状态**: Draft
**关联**: [Phase 3 Spec](phase3-enhancements-spec.md) §5.1.3
**依赖**: Module 4 (Orchestrator Core, AgentExecutor.execute_chain)

## 1. 范围

Chain pipeline 完整执行 + 前端折叠卡片增强。

## 2. 后端

### AgentExecutor.execute_chain() 完善

```python
async def execute_chain(calls: list[AgentCall]) -> AsyncIterator[TokenEvent]:
    """链式: call[0] 产出 → call[1] 输入 → call[2]..."""
    previous_output = ""
    for i, call in enumerate(calls):
        if i > 0:
            # 上一步产出注入 prompt（截断保护）
            truncated = previous_output[:2000]
            call.input_messages.append({
                "role": "assistant",
                "content": f"[上一步产出]\n{truncated}"
            })

        # 发送 chain_step 事件
        yield ChainStepEvent(step=i, agent=call.agent.name, total=len(calls))

        async for ev in execute_single(call):
            if ev.token and not ev.done:
                previous_output += ev.token
            yield ev
```

### 触发条件

- GroupChatCreator 中配置 chain (A → B)
- 存储为 session 的 `chain_config` JSON 字段
- Pipeline Stage 3 检测 chain_config → 模式设为 "chain"

## 3. 前端: CollabProgressCard 增强

- 折叠状态: "协作进行中 (2/3 步完成)" + 进度条
- 展开状态: 每步显示 Agent 名称 + 状态指示器 (pending/running/done/error)
- 完成后: 默认折叠，可展开查看中间步骤产出摘要

## 4. 验收标准

- [ ] 链式配置 → A 产出完成 → B 自动收到 A 输出作为输入
- [ ] 中间步骤折叠为摘要卡片，完成后可展开
- [ ] 链式中断 (A 失败) → 显示 "链式协作在步骤 1 中断"

## 5. 测试

- Unit: chain 顺序验证 + 输出注入 + 中断处理 → 6 条
- 前端: CollabProgressCard 折叠/展开 → 6 条
- 目标: 12 条

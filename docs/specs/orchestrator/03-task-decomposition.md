# 03 — 任务拆解与 DAG 依赖模型

**关联实现**: `backend/app/domain/task_decomposer.py`, `backend/app/domain/execution_planner.py`

---

## 1. 概述

TaskDecomposer 判断用户请求是否需要拆解。如果需要，按意图类型匹配模板，生成带角色和依赖的子任务列表。ExecutionPlanner 将子任务列表拓扑排序为 Phase DAG。

## 2. 复杂请求检测

### 2.1 复杂标记 (is_complex)

检测到以下关键词 → `is_complex() = True`:

```
"前后端", "API+", "全栈", "前端和后端", "都要",
"同时", "一起", "以及", "还有", "并且"
```

`is_complex() = True` 不自动触发链式 — 它只表示任务需要拆解。最终模式由 ExecutionPlanner 的优先级链决定。

### 2.2 多阶段标记 (is_chain)

检测到以下关键词 → `is_chain() = True`:

```
"先", "再", "然后", "最后", "之后",
"设计并实现", "从设计到",
"调研并总结", "分析并优化"
```

`is_chain() = True` → ExecutionPlanner 自动设置 `mode="chain"`。

---

## 3. 角色系统

### 3.1 6 种模板角色

| 角色 | 职责 | Prompt 注入 |
|------|------|------------|
| `planner` | 分析需求，制定方案架构 | "你需要制定详细的技术方案，不写具体代码。" |
| `executor` | 按方案产出具体内容 | "按照上一步的方案，产出具体实现。" |
| `reviewer` | 审查产出质量 | "审查以上产出，指出问题和改进建议。" |
| `researcher` | 收集信息 | "搜索和收集相关信息，整理为结构化材料。" |
| `synthesizer` | 综合多源信息 | "综合以上信息，形成最终结论。" |
| `critic` | 质疑和补充 | "找出方案的漏洞、遗漏和风险点。" |

Phase 3 模板驱动，Phase 4 升级 LLM 动态分配。

### 3.2 Agent 匹配策略

```python
def _match_agent_for_subtask(subtask, agents):
    """为子任务匹配最合适的 Agent: 按 subtask.tags 在 agent 元数据中搜索。"""
    for agent in agents:
        search = f"{agent.description} {agent.system_prompt} {agent.name}"
        score = sum(1 for tag in subtask.tags if tag.lower() in search.lower())
    return best_score_agent
```

---

## 4. 拆解模板 (DAG v2)

### 4.1 SubTask 数据模型

```python
@dataclass
class SubTask:
    name: str                          # "planning" | "frontend" | "backend" | "review"
    role: str                          # planner | executor | reviewer | researcher | synthesizer | critic
    description: str                   # 注入 Prompt 的任务描述
    tags: list[str]                    # 匹配 Agent 能力的关键词
    depends_on: list[str] = []         # 依赖的 task name (DAG 边)
    phase: int = 0                     # ExecutionPlanner 拓扑排序后分配
```

### 4.2 意图 → 模板映射

```python
TASK_TEMPLATES = {
    "code_gen": [
        SubTask("planning", "planner",
                "分析需求，制定技术方案和架构设计，不写具体代码",
                ["架构", "设计", "方案"],
                depends_on=[]),
        SubTask("frontend", "executor",
                "按照技术方案实现前端界面和交互逻辑",
                ["前端", "React", "UI", "组件"],
                depends_on=["planning"]),
        SubTask("backend", "executor",
                "按照技术方案实现后端 API 和数据库",
                ["后端", "API", "数据库", "Python"],
                depends_on=["planning"]),
        SubTask("review", "reviewer",
                "审查前端和后端代码的质量、安全性和一致性",
                ["审查", "测试", "安全"],
                depends_on=["frontend", "backend"]),
    ],
    "research": [
        SubTask("search", "researcher",
                "搜索和收集相关资料与数据",
                ["搜索", "分析", "调查"],
                depends_on=[]),
        SubTask("synthesize", "synthesizer",
                "综合搜索和分析结果，形成结构化结论",
                ["写作", "总结", "综合"],
                depends_on=["search"]),
        SubTask("critique", "critic",
                "批判性审视结论，找出漏洞、遗漏和风险点",
                ["批判", "检查", "验证"],
                depends_on=["synthesize"]),
    ],
    "design_ui": [
        SubTask("concept", "planner",
                "分析用户需求，制定视觉设计策略和设计系统",
                ["设计", "UI", "UX"],
                depends_on=[]),
        SubTask("execution", "executor",
                "按照设计策略产出具体 UI 组件和样式代码",
                ["前端", "CSS", "组件"],
                depends_on=["concept"]),
        SubTask("review", "reviewer",
                "审查设计的可用性、一致性和可访问性",
                ["审查", "测试", "UI"],
                depends_on=["execution"]),
    ],
}
```

### 4.3 拓扑排序 → Phase 分配

`ExecutionPlanner._assign_phases()` 方法:

1. 收集所有 `depends_on = []` 的 SubTask → Phase 0
2. 找到所有依赖已满足的 SubTask → Phase 1
3. 重复直到所有 SubTask 分配完毕
4. Phase 内可并行（`mode="parallel"`），Phase 间串行

```
code_gen DAG:

Phase 0 [串行]:  planning (depends_on=[])
    │
    ▼
Phase 1 [并行]:  frontend (depends_on=["planning"])
                 backend  (depends_on=["planning"])
    │
    ▼
Phase 2 [串行]:  review (depends_on=["frontend","backend"])
```

---

## 5. 当前实现状态

| 功能 | 状态 | 备注 |
|------|------|------|
| is_complex 检测 | ✅ | 关键词匹配 |
| is_chain 检测 | ✅ | 关键词匹配 |
| 6 角色模板 | ✅ | 3 套模板 (code_gen/research/design_ui) |
| Agent 标签匹配 | ✅ | 按 subtask.tags 在 agent 元数据中搜索 |
| SubTask.depends_on | ❌ 未实现 | 当前模板无 depends_on 字段 |
| 拓扑排序 | ❌ 未实现 | 当前全并行 or 全串行，不混合 |
| Phase 分配 | ❌ 未实现 | 依赖拓扑排序 |

**下一步**: SubTask 增加 `depends_on` → ExecutionPlanner 实现 `_assign_phases()` → 见 `08-dev-plan.md`。

# 02 — 意图分析与 Agent 选择

**关联实现**: `backend/app/domain/intent_analyzer.py`, `backend/app/domain/agent_selector.py`

---

## 1. IntentAnalyzer (意图分析器)

### 1.1 职责

从用户消息中提取 **意图类型** + **能力需求标签**。关键词规则匹配，Phase 3 实现。

### 1.2 数据模型

```python
@dataclass
class IntentAnalysis:
    intent: str = "general_qa"      # code_gen | research | design_ui | general_qa
    required_tags: list[str] = []   # 能力需求标签 (供 AgentSelector 匹配)
    confidence: float = 0.3         # 关键词匹配=1.0, 降级=0.3
    evidence: str = ""              # 匹配到的关键词，调试用
```

### 1.3 意图类型与关键词映射

| 意图 | 典型关键词 | 基础标签 | 示例用户输入 |
|------|-----------|---------|-------------|
| `code_gen` | 写代码、实现、开发、修复bug、API、组件、函数 | `["开发", "代码", "编程"]` | "帮我写一个 React 登录组件" |
| `research` | 调研、分析、比较、推荐、优缺点、对比 | `["调研", "分析", "比较"]` | "对比 React 和 Vue 的优缺点" |
| `design_ui` | UI、界面、设计、样式、CSS、布局、美化 | `["UI", "设计", "前端", "样式"]` | "设计一个好看的按钮样式" |
| `general_qa` | (无匹配时的默认) | `["通用"]` | "今天天气怎么样" |

### 1.4 技术标签提取

从用户消息中提取 **14 个技术维度**的能力标签，用于 Agent 匹配：

```python
TECH_TAG_PATTERNS = {
    "React":    ["react", "jsx", "tsx", "hooks"],
    "Python":   ["python", "flask", "fastapi", "django"],
    "API":      ["api", "接口", "rest", "端点"],
    "数据库":    ["数据库", "sql", "mysql", "postgresql"],
    "认证":      ["登录", "注册", "auth", "jwt", "token"],
    "前端":      ["前端", "frontend", "页面", "组件"],
    "后端":      ["后端", "backend", "服务端"],
    "测试":      ["测试", "test", "单元测试"],
    "部署":      ["部署", "deploy", "docker"],
    "安全":      ["安全", "security", "加密"],
    "性能":      ["性能", "performance", "优化", "缓存"],
    "架构":      ["架构", "architecture", "设计模式"],
    "算法":      ["算法", "algorithm", "数据结构"],
    "TypeScript":["typescript", "ts", "类型"],
}
```

### 1.5 分析示例

```
输入: "帮我写一个 React 前端登录页面，需要数据库和后端 API"

输出: IntentAnalysis(
    intent="code_gen",
    required_tags=["开发", "代码", "编程", "React", "前端", "认证", "数据库", "API", "后端"],
    confidence=1.0,
    evidence="matched keyword: '前端'"
)
```

---

## 2. AgentSelector (Agent 选择器)

### 2.1 核心原则

**Agent ≠ Provider。** 当前 Agent 是用户接入的本机 CLI 工具实例（Claude Code / Codex / OpenCode / custom）。AgentSelector 只根据名称、备注和可选 system_prompt 元数据做任务匹配；执行能力来自 CLI 配置和本机登录态。DeepSeek 只作为后端内部系统模型，不参与用户 Agent 选择。

### 2.2 数据模型

```python
@dataclass
class ScoredAgent:
    agent: AgentConfig
    score: int
    match_tags: list[str]   # 命中的能力标签
    reason: str              # exact_mention | tag_match | fallback
```

### 2.3 选择策略（三级优先级）

```
优先级 1: @mention 精确匹配
  └─ 条件: mentions 列表非空, agent.id in mentions
  └─ 得分: MAX_MENTION_SCORE (9999)
  └─ 原因: "exact_mention"
  └─ 行为: 只返回被 @ 的 Agent, 其他全部排除

优先级 2: 能力标签匹配
  └─ 条件: required_tags 在 agent.description + agent.system_prompt + agent.name 中命中
  └─ 权重: name 命中 = 3分, description 命中 = 2分, system_prompt 命中 = 1分
  └─ 原因: "tag_match"

优先级 3: Fallback
  └─ 条件: 无标签匹配
  └─ 得分: FALLBACK_SCORE (1)
  └─ 原因: "fallback"
```

### 2.4 匹配搜索空间

```python
search_text = f"{agent.name} {agent.description} {agent.system_prompt}"
```

Agent 创建的三个字段都在匹配范围内。用户可以用名称或备注区分多个本机 CLI 配置；这些元数据只影响 Orchestrator 路由，不代表 AgentHub 创建了新的 HTTP 模型助手。

### 2.5 评分示例

```
Agent A: name="前端专家", description="React前端开发", system_prompt="擅长React"
Agent B: name="后端架构师", description="Python后端API", system_prompt="擅长FastAPI"

required_tags = ["React", "前端"]

Agent A: "React" 命中 name(+3) + description(+2) + system_prompt(+1) = 6
         "前端" 命中 name(+3) = 3
         总分 = 9, reason = "tag_match"

Agent B: "React" 0分, "前端" 0分
         总分 = 1, reason = "fallback"

结果: [Agent A (9分), Agent B (1分)]
```

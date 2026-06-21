# Phase 3 审计报告

**文档编号**: AUDIT-2026-0602
**审计日期**: 2026-06-02
**审计范围**: Phase 3 全流程（规划、开发、文档、架构）
**关联**: [ADR-0008](../../../adr/0008-revised-development-strategy.md) (修订开发策略)

---

## 1. 执行摘要

Phase 3 原计划实现 8 个模块（基础设施 + Orchestrator + 消息操作 + 搜索 + 链式协作 + 产物版本 + 在线编辑 + 收尾），实际完成度为：**基础设施 (100%) + Orchestrator (100%)，其余 6 个模块 0%**。

核心问题不是"做得太少"，而是"在单一方向（Orchestrator）过度深耕，导致其他同等重要的功能板块完全空白"。这违反了 ADR-0004 的"每个增量可演示"原则——Phase 3 结束后，用户无法使用消息回复、搜索、产物版本等直接感知功能。

此外，PRD 文档定义的核心架构基础（CLI Agent 封装 via PTY/subprocess）完全未实现。当前代码走向了 PRD 明确批判的"HTTP API Adapter"路线。

---

## 2. PRD 符合性矩阵

### 2.1 PRD-00 (Master Hub) 核心指标达成

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| 复杂任务闭环率 | >75% | N/A (tasks/task_dependencies 表不存在) | ❌ |
| 人工干预频率 | N/A | 无人工审批断点功能 | ❌ |
| 产物抽屉打开率 | >90% | 三栏布局 + 产物抽屉未实现 | ❌ |
| CLI 进程异常崩溃率 | <2% | CLI 适配器未实现 | ❌ |

### 2.2 PRD-01 (CLI Adapter) 符合性

| 需求 | 实际 | 状态 |
|------|------|------|
| PTY / subprocess 进程孵化 | 不存在 | ❌ |
| CWD 统一管理 + 环境变量隔离 | 不存在 | ❌ |
| ANSI 转义码清洗 | 不存在 | ❌ |
| 交互式提示拦截 (y/n → 前端卡片) | 不存在 | ❌ |
| 僵尸进程防范 (心跳 + SIGTERM/SIGKILL) | 不存在 | ❌ |
| BaseAgentAdapter 接口 | ✅ 存在，但仅用于 HTTP API 调用 | ⚠️ 偏离 |

### 2.3 PRD-02 (Orchestrator Engine) 符合性

| 需求 | 实际 | 状态 |
|------|------|------|
| 意图分析 + 任务拆解 (WBS) | ✅ IntentAnalyzer + TaskDecomposer | ✅ |
| DAG 任务依赖模型 | ✅ SubTask.depends_on + 拓扑排序 | ✅ |
| 任务状态机 (PENDING/RUNNING/PAUSED/COMPLETED/FAILED) | ⚠️ 只在内存中，无数据库持久化 | ⚠️ |
| 并发调度 (无依赖任务并行) | ✅ AgentExecutor._execute_parallel | ✅ |
| 人工审批断点 (Human-in-the-loop) | ❌ 无 PAUSED 状态的前端阻断卡片 | ❌ |
| 断点续传 (FAILED → 重试) | ❌ 无持久化，重启即丢失 | ❌ |
| 定向上下文注入 | ✅ SharedContext + Chain 注入 | ✅ |
| tasks / task_dependencies 数据库表 | ❌ 不存在这两个表 | ❌ |

### 2.4 PRD-03 (User Experience) 符合性

| 需求 | 实际 | 状态 |
|------|------|------|
| 动态三栏布局 (Sidebar + Chat + Drawer) | ❌ 无右区产物抽屉 | ❌ |
| 资产卡片 (Asset Card) | ⚠️ ArtifactCard 基础版，无版本选择器 | ⚠️ |
| 代码 Diff 视图 (Monaco) | ❌ | ❌ |
| IFrame 网页预览 | ❌ | ❌ |
| 空状态首屏 (问候语 + 快捷胶囊) | ⚠️ ChatInput 存在，但无问候语 | ⚠️ |
| 环境体检卡片 | ❌ | ❌ |
| DAG 任务看板 | ✅ CollaborationPanel | ✅ |
| 人工审批阻断卡片 | ❌ | ❌ |
| 打字机流推 (SSE Typewriter) | ✅ | ✅ |
| 卡片呼吸灯 | ❌ | ❌ |

### 2.5 PRD-04 (Data & API) 符合性

| 需求 | 实际 | 状态 |
|------|------|------|
| agents 表 (含 executable, init_args) | ❌ 是 AgentConfig 表，无 CLI 字段 | ⚠️ |
| sessions 表 | ✅ | ✅ |
| messages 表 (含 reply_to_id) | ⚠️ parent_message_id 列存在，但 reply 功能未实现 | ⚠️ |
| tasks 表 | ❌ 不存在 | ❌ |
| task_dependencies 表 | ❌ 不存在 | ❌ |
| POST /api/sessions/{id}/orchestrate | ❌ Orchestrator 触发是隐式的 (通过 chat API) | ⚠️ |
| POST /api/tasks/{id}/approve | ❌ | ❌ |
| GET /api/sessions/{id}/stream (SSE) | ✅ | ✅ |
| POST /api/sessions/{id}/input | ✅ | ✅ |
| FTS5 全文搜索 | ❌ FTS5 虚拟表已创建，但搜索 API 未实现 | ⚠️ |

---

## 3. 模块完成度矩阵

| Module | 名称 | 后端 | 前端 | 测试 | 状态 |
|--------|------|------|------|------|------|
| M1 | 基础设施 | ✅ 100% | N/A | 68 条 | ✅ COMPLETED |
| M2 | 消息操作 (reply/regenerate/pin) | ❌ 0% | ❌ 0% | 0 条 | ❌ 未开始 |
| M3 | 消息搜索 (FTS5) | ❌ 0% | ❌ 0% | 0 条 | ❌ 未开始 |
| M4 | Orchestrator 核心 | ✅ 100% | ✅ 100% | 154 条 | ✅ COMPLETED |
| M5 | 链式协作 | ✅ (合并入 M4) | ✅ (合并入 M4) | ↑ | ✅ COMPLETED |
| M6 | 产物版本 + Diff | ❌ 0% | ❌ 0% | 0 条 | ❌ 未开始 |
| M7 | 产物在线编辑 | ❌ 0% | ❌ 0% | 0 条 | ❌ 未开始 |
| M8 | Store 拆分 + 体验收尾 | ⚠️ 部分 | ⚠️ 部分 | 8 条 | ⚠️ 部分完成 |

---

## 4. 架构偏离分析

### 4.1 核心偏离：HTTP API vs CLI Wrapper

```
PRD 设计:  CLI Agent (claude命令) → PTY → stdout/stderr → ANSI清洗 → SSE
实际实现: HTTP API Key → LLM Provider REST API → SSE

PRD 明确批判: "造轮子成本极高...脱离主流开源生态...违反课题初衷"
代码实现: 正是这个被批判的模式
```

**影响范围**：
- 无法调用真实的 Claude Code CLI 工具（课题核心要求）
- 无法享受 CLI 工具的原生文件系统读写能力
- 无法实现交互式审批（y/n 拦截）
- 与 PRD 的"Agent-as-a-Service"定位脱节

### 4.2 偏离原因分析

1. **开发便利性**: HTTP API 适配器开发成本远低于 PTY 进程管理
2. **时间压力**: Phase 3 的时间被 Orchestrator 的深度开发占满
3. **架构决策缺失**: 没有 ADR 记录"为什么放弃 CLI 路线选择 HTTP API 路线"
4. **渐进式偏离**: 从 Phase 1 开始就是 HTTP API，Phase 2 延续，Phase 3 没有回头审视

---

## 5. 开发策略缺陷分析

### 5.1 旧策略 (Phase 3 8 模块并行)

**设计假设**: 8 个模块可以并行开发，通过接口契约解耦
**实际结果**: 只有 M1 + M4/M5 完成，其余 5 个模块 0%

**缺陷根因**:
1. **难度偏差**: 选择了最高复杂度的 M4 (Orchestrator) 深度投入，消耗全部带宽
2. **虚假并行**: "可并行"的理论被实际资源限制打破——同一开发者无法同时做 3 个模块
3. **缺乏硬边界**: 没有"不完成当前板块就不能进入下一板块"的硬约束
4. **增量不可演示**: 做完 M4 后，用户看到的仍是 Phase 2 的 UI，没有新功能感知

### 5.2 新策略 (Phase 4-7 功能板块制)

详见 [ADR-0008](../../../adr/0008-revised-development-strategy.md)。

**关键变更**:
- 每板块独立完整交付 → 用户可感知的渐进式改进
- 按用户价值排序 → Phase 4 (消息交互) > Phase 5 (产物) > Phase 6 (Workspace + CLI) > Phase 7 (UX)
- 硬边界约束 → 当前板块未通过验收，不得开下一板块

---

## 6. 文档债清单

### 6.1 已修复 (本次审计)

| 问题 | 修复 |
|------|------|
| ADR 编号与文件名不一致 (0006 内部写 0007, 0007 内部写 0008) | ✅ 统一为文件名编号 |
| SPEC_TEMPLATE.md 存在但无人使用 | ✅ 保留，各 Phase README 中引用 |
| CONTEXT.md 引用不存在文件 (ONBOARDING/FIRST_ISSUES) | ✅ 移除无效引用，替换为当前入口 README.md |
| `phase3-enhancements-spec.md` 被 10+ 处引用但从未创建 | ✅ 引用替换为 PRD 文档链接 |
| AgentHub-多Agent协作平台设计.md / Trae.md 散落根目录 | ✅ 移入 archive/ |
| Phase 1/2 dev-log 散落 docs/ 根目录 | ✅ 移入 dev-logs/ |
| Phase 3 无独立开发日志 | ✅ 已创建 (见 dev-logs/phase3-dev-log.md) |

### 6.2 遗留建议

| 建议 | 优先级 |
|------|--------|
| 创建 ONBOARDING.md（新成员入门指南） | P2 |
| 创建 README.md（项目根目录说明） | P3 |
| Phase 2 Spec 内部分内容可能与 PRD 重叠，需要去重 | P3 |

---

## 7. 后续行动清单

| 序号 | 行动 | 关联 |
|------|------|------|
| 1 | **Phase 4 启动**: 消息交互闭环 (reply/regenerate/pin/search) | ADR-0008 §4 |
| 2 | Phase 5: 产物工作台能力 (版本+Diff+在线编辑) | ADR-0008 §5 |
| 3 | Phase 6: Workspace Runtime + CLI 适配器 + 产物入口桥接 | ADR-0008 §6 |
| 4 | Phase 7: UX 体验闭环 + MVP 演示闭环 | ADR-0008 §7 |
| 5 | 每次 Phase 结束时执行本报告同级审计 | ADR-0008 §9 |
| 6 | 创建 ONBOARDING.md 完善新成员入门路径 | P2 |

---

## 8. 审计结论

Phase 3 的核心成果（Orchestrator v2 + CollaborationPanel + EventBus + 154 条测试）是高质量的工程交付。但代价是：
- **架构基础缺失**：PRD 定义的 CLI Agent 封装核心能力归零
- **用户感知功能空白**：消息交互、搜索、产物管理等直接体验功能归零
- **文档熵增**：编号错位、幽灵引用、散落文件

后续 Phase 4-7 采用功能板块制，确保每个板块完整可演示后再进入下一板块。Workspace Runtime + CLI 适配器（Phase 6）作为架构基础修正，必须在 Phase 7 之前完成。

**评级**: Phase 3 — **部分成功**（Orchestrator 模块 A+ / 整体交付 C / 架构符合性 D）

---

> **版本**: v1.0 | **下次审计**: Phase 4 完成时

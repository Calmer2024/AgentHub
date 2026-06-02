# ADR-0008: 修订开发策略 —— 功能板块制 + Phase 4-7 路线图

**Date**: 2026-06-02
**Status**: Accepted
**Replaces**: Phase 3 并行开发指南 (`docs/specs/planning/phase3-parallel-guide.md`), Phase 3 模块化计划 (`docs/specs/planning/phase3-modules.md`) 中的开发顺序部分

---

## 1. Context

### 1.1 问题诊断

Phase 3 采用"8 模块并行 + 增量叠加"的开发策略。经过完整执行，暴露出以下系统性问题：

| 问题 | 表现 | 根因 |
|------|------|------|
| **深度不均** | Orchestrator 投入 154 条测试、9 篇设计文档、全 DAG 可视化；消息操作/搜索/产物管理投入为 0 | 过早在一个方向深耕，忽略其他板块 |
| **板块空白** | Phase 3 Spec 规划的 8 个模块中，M2(消息操作)、M3(搜索)、M6(产物版本)、M7(在线编辑)、M8(收尾) 全部未动工 | "先做难的再补简单的"策略导致简单模块持续后延 |
| **架构偏离** | PRD 核心设计（CLI Agent 封装 via PTY/subprocess）完全未实现，代码走的是 HTTP API Adapter 路线 | Phase 3 的 Orchestrator 需求挤压了架构基础建设的时间 |
| **不可演示** | Phase 3 完成后，只有 Orchestrator 相关功能可演示。消息搜索、产物版本等用户直接感知的功能为零 | 违反了 ADR-0004 "每个增量都必须可演示"原则 |
| **文档熵增** | ADR 编号错位、Spec 文件平铺无层级、不存在的文件被多处引用 | 文档随代码增量滚动更新，缺乏周期性审计 |

### 1.2 核心洞察

> **当前策略的问题不是"做得太少"，而是"在一个方向做得太深，其他方向做得太浅"。**

Phase 3 的 Orchestrator 成果（Pipeline 四阶段、DAG 混合调度、6 角色模板、CollaborationPanel）是高质量的，但它占用了 Phase 3 的全部带宽，导致其他同等重要的功能板块处于零状态。后续开发必须纠正这种"单点深挖"的模式。

---

## 2. Decision

### 2.1 新策略：功能板块制 (Functional Block System)

**核心原则**：

1. **每个 Phase = 一个独立的功能板块**。板块内包含该功能领域的全部子模块（后端 + 前端 + 测试）。
2. **板块内做到 PRD 级别完整**后才进入下一板块。不允许"所有板块都碰一点"。
3. **每个板块结束时必须有可演示的完整功能**。用户可以直接使用该板块的全部能力。
4. **板块之间按用户可感知价值排序**。优先实现用户能直接看到和使用的功能。
5. **架构基础板块放在中间**。既不因为架构洁癖阻塞 UX 功能，也不无限期推迟架构修正。

### 2.2 Phase 4-7 板块划分

```
Phase 4: 消息交互闭环 ──── 用户可直接使用 reply/regenerate/pin/search
Phase 5: 产物深度管理 ──── 版本历史、Diff 对比、局部编辑
Phase 6: CLI 适配器 ────── PRD 架构基础：PTY 进程管理、ANSI 清洗、交互拦截
Phase 7: UX 体验闭环 ──── 三栏布局、产物抽屉、审批卡片、全局打磨
```

### 2.3 每个板块的内部结构

每个 Phase 内部遵循统一模板：

```
Phase N/
├── README.md              ← 板块总览 + 验收标准清单
├── 01-<module-a>.md       ← 子模块 Spec
├── 02-<module-b>.md       ← 子模块 Spec
└── (可选) 03-<module-c>.md
```

每个子模块 Spec 必须覆盖：
- 后端 API + Service + 数据模型
- 前端组件 + Store + 交互状态
- 测试标准（Unit + API + E2E 最低数量）
- 与其他 Phase 的接口契约

### 2.4 板块间依赖关系

```
Phase 3 (已完成) ──── 基础设施 + Orchestrator
    │
    ├── Phase 4: 消息交互闭环
    │    依赖: Phase 3 (MessageService ABC, DB 列)
    │
    ├── Phase 5: 产物深度管理
    │    依赖: Phase 3 (Artifact 模型), Phase 4 完成后用户体验完整
    │
    ├── Phase 6: CLI 适配器
    │    依赖: Phase 3 (BaseAgentAdapter), 独立于 Phase 4/5
    │    注意: 新增 CLI 适配器类型，不影响现有 HTTP 适配器
    │
    └── Phase 7: UX 体验闭环
         依赖: Phase 4 + Phase 5 + Phase 6 全部完成
```

Phase 4 和 Phase 5 之间没有强依赖，但建议串行完成以保证每板块的专注度。Phase 6 可以与 Phase 4/5 并行（操作不同代码区域）。

---

## 3. Phase 3 完成状态确认

Phase 3 更名为"Orchestrator + 基础设施"，其实际交付内容：

| 交付物 | 状态 | 说明 |
|--------|------|------|
| EventBus + 数据库迁移 + Service ABC | ✅ | Module 1 基础设施 |
| Orchestrator Pipeline (4 阶段) | ✅ | IntentAnalyzer + AgentSelector + TaskDecomposer + ExecutionPlanner |
| AgentExecutor (single/parallel/chain/dag) | ✅ | 含超时、中断、全失败兜底 |
| SharedContext + 中枢总结 | ✅ | 对话流共享 + 定向注入 + OrchestratorSummarizer |
| CollaborationPanel + Agent 角色气泡 | ✅ | DAG 可视化 + 角色标签 |
| SSE 协议 (6 + phase_change 事件) | ✅ | 前后端事件协议标准化 |
| HTTP Agent Adapters (6 厂商) | ✅ | DeepSeek/Gemini/GLM/MiniMax + OpenAI/Claude |

**未完成（移入后续 Phase）**：
- 消息 reply/regenerate/pin → Phase 4
- 消息全文搜索 → Phase 4
- 产物版本 + Diff → Phase 5
- 产物在线编辑 → Phase 5
- CLI PTY 适配器 → Phase 6
- 三栏动态布局 → Phase 7

---

## 4. Phase 4: 消息交互闭环

**状态更新 (2026-06-02)**: Completed。实现与验收记录见 [Phase 4 Spec](../specs/phase4/README.md) 和 [Phase 4 Dev Log](../dev-logs/phase4-dev-log.md)。

### 4.1 目标

用户可以在聊天中引用历史消息、重新生成 AI 回复、Pin 关键上下文、全文搜索历史对话。

### 4.2 子模块

**Module 4A: 消息操作 (reply/regenerate/pin)**
- `POST /api/messages/{id}/reply` — 引用回复
- `POST /api/messages/{id}/regenerate` — SSE 流式重新生成
- `POST/DELETE /api/messages/{id}/pin` — Pin/Unpin
- `MessageActions.tsx` — hover 操作按钮栏
- `ReplyPreview.tsx` — 输入框引用卡片
- `SqlAlchemyMessageService` 实现 MessageService ABC

**Module 4B: 全文搜索 (FTS5)**
- `GET /api/messages/search?q=&session_id=&limit=` — FTS5 + LIKE fallback
- `SearchPanel.tsx` — 搜索框 + 结果列表 + 高亮跳转
- FTS5 中文分词支持

### 4.3 验收标准
- [x] 引用消息 → 气泡显示引用预览 → 点击跳转原消息
- [x] 引用消息不是 UI-only：`parentMessageId` + `metadata.replyReference` 落库，`[Reply context]` 注入 Agent 输入，真实 UI 验收证明 Agent 可感知引用内容
- [x] 重新生成 → 旧内容保留 + SSE 流式替换 → 超时回退
- [x] Pin 消息 → 上下文注入优先级 → 超出预算时自动淘汰最旧 Pin
- [x] 搜索中文关键词 → 返回高亮结果 → 点击跳转并闪烁定位
- [x] 所有操作在单聊和群聊中均可用

### 4.4 原始预估
- 后端: ~300 LOC (message_service_impl 补充 + search endpoint)
- 前端: ~400 LOC (MessageActions + ReplyPreview + SearchPanel)
- 测试: 30 条 (Unit 10 + API 12 + E2E 8)

---

## 5. Phase 5: 产物深度管理

### 5.1 目标

产物（代码/文档/网页）拥有版本历史、可视化 Diff、支持选中区域局部编辑。

### 5.2 子模块

**Module 5A: 产物版本 + Diff**
- `GET /api/artifacts/{id}/versions` — 版本链查询
- `GET /api/artifacts/{id}/diff?v1=&v2=` — unified_diff
- `VersionHistory.tsx` — 版本下拉选择器
- `DiffViewer.tsx` — 左右对比/统一视图

**Module 5B: 产物在线编辑**
- `POST /api/artifacts/{id}/edit` — 选中片段修改
- `edit_artifact` tool schema → Agent Tool Calling 集成
- `CodeSelector.tsx` — 代码区域选中
- Diff 确认/拒绝 UI

### 5.3 验收标准
- [ ] 产物重新生成后 → 自动创建新版本 → 版本选择器可回溯
- [ ] 选择两个版本 → 并排 Diff 视图 → 增删行高亮
- [ ] 选中代码片段 → 输入修改意图 → Agent 返回 Diff → 用户确认/拒绝
- [ ] 不支持 tool_call 的 Agent → 降级为上下文注入

### 5.4 预估
- 后端: ~400 LOC
- 前端: ~500 LOC
- 测试: 45 条

---

## 6. Phase 6: CLI 适配器 (Architecture Foundation Fix)

### 6.1 目标

实现 PRD-01 定义的 CLI Agent 封装能力：通过 PTY/subprocess 管理真实 CLI 工具（Claude Code 等），支持 stdout 流式推送、ANSI 转义码清洗、交互式提示拦截。

### 6.2 子模块

**Module 6A: CLI Process Manager**
- `subprocess`/`PTY` 进程孵化与生命周期管理
- CWD 统一管理 + 环境变量隔离
- 心跳超时 + 僵尸进程清理 (SIGTERM/SIGKILL)

**Module 6B: Stream Sanitizer (ANSI 清洗)**
- ANSI 转义码正则过滤
- 分块 SSE 推送（50ms 批量）
- 进度条/表格等复杂 TUI 组件的降级渲染

**Module 6C: Interactive Prompt Interception**
- 滑动窗口缓冲区 + 阻塞特征正则匹配（如 `(y/n)`）
- 暂停流推送 → 前端信令卡片 → stdin 回写唤醒

**Module 6D: CLI Agent Adapter (新增)**
- `CliAgentAdapter` 实现 `BaseAgentAdapter` 接口
- 与现有 HTTP 适配器并存（`agent_type` 新增 `cli_wrapper`）

### 6.3 验收标准
- [ ] 后端启动 `claude` CLI → stdout 实时推流到前端 → 打字机效果流畅
- [ ] ANSI 颜色码被正确过滤 → 前端收到纯净 Markdown
- [ ] Claude Code 发出 `(y/n)` 确认 → 前端弹出交互卡片 → 用户点击后进程继续
- [ ] 用户关闭网页 → 3 分钟后进程被 SIGTERM
- [ ] 5 分钟无 stdout → 判定死锁 → SIGKILL
- [ ] CliAgentAdapter 可在 AgentPanel 中选择配置

### 6.4 预估
- 后端: ~600 LOC (process_manager + stream_sanitizer + prompt_interceptor + cli_adapter)
- 前端: ~200 LOC (InteractivePromptCard + AgentPanel CLI 配置)
- 测试: 35 条

---

## 7. Phase 7: UX 体验闭环 + 集成收尾

### 7.1 目标

实现 PRD-03 定义的三栏动态布局、产物抽屉、人工审批卡片、环境体检，全局 Store 拆分，UX 打磨。

### 7.2 子模块

**Module 7A: 动态三栏布局 + 产物抽屉**
- 右区 Artifact Drawer（宽度 0 → 40-50%，可拖拽）
- 抽屉内部：代码 Diff / 网页预览 双态切换
- 资产卡片增强（图标 + 版本号 + 预览/引用按钮）

**Module 7B: 人工审批断点**
- `requires_human_approval` → 任务状态 PAUSED
- 前端阻断卡片（红色警戒线 + 确认/驳回按钮）
- 输入框暂停遮罩（允许 @ 辩论）

**Module 7C: 环境体检卡片**
- 左栏底部：检测 Claude Code/Docker/Node.js 可用性
- 绿/红状态指示灯

**Module 7D: Store 拆分 + 全局 UX**
- chatStore / sessionStore / searchStore 独立文件
- P0/P1 UX 缺陷清零
- 全量回归测试

### 7.3 验收标准
- [ ] 点击资产卡片 [预览产物] → 右区抽屉滑出（40% 宽度）→ 可拖拽调整宽度
- [ ] 抽屉内 [网页预览] 模式 → IFrame 真实渲染
- [ ] 抽屉内 [代码 Diff] 模式 → Monaco 并排对比
- [ ] 审批断点触发 → 聊天流底部阻断卡片 → 用户确认后流水线继续
- [ ] 环境体检卡片 → 实时检测 → 异常时红字告警
- [ ] 全量回归零失败

### 7.4 预估
- 后端: ~250 LOC
- 前端: ~600 LOC
- 测试: 25 条

---

## 8. 策略对比

| 维度 | 旧策略 (Phase 3) | 新策略 (Phase 4-7) |
|------|-----------------|-------------------|
| **组织方式** | 8 模块并行，按复杂度分配 | 4 板块串行，按用户价值排序 |
| **完成标准** | 模块独立交付 | 板块内全功能可演示 |
| **文档结构** | 平铺在 specs/ 根目录 | 每个 Phase 独立目录 |
| **架构基础** | 推迟到"以后" | Phase 6 专项修正 |
| **UX 优先级** | 最后 (M8 收尾) | Phase 7 独立板块 |
| **Orchestrator 深度** | 过度投入（154 条测试） | 已完成，不再追加 |
| **跨模块依赖** | 复杂矩阵 (见旧 parallel-guide) | 简化：Phase N 只依赖 Phase N-1 和 Phase 3 |

---

## 9. 文档治理规则（新增）

为保持文档脉络清晰，制定以下周期性质控规则：

1. **Phase 结束时审计**：每个 Phase wrap-up 时检查所有 docs/ 下的交叉引用是否有效
2. **ADR 编号与文件名一致**：`NNNN-title.md` 内部标题必须是 `ADR-NNNN`
3. **Spec 文件必须被 CONTEXT.md 索引**：不被索引的 Spec = 不会被 AI 发现 = 无效文档
4. **旧文档立即归档或删除**：不再适用的文档移入 `docs/archive/`，不留在原位产生混淆
5. **一个事实一个权威源**：同一信息不出现在两个地方。如果需要引用，用链接，不复制。

---

## 10. Consequences

- Phase 4-7 每个板块严格独立，不允许跨板块同时开发
- Phase 3 的 Orchestrator 成果被冻结为基础设施，后续板块在其上构建但不再追加 Orchestrator 功能
- CLI 适配器（Phase 6）作为新增能力，不影响现有 HTTP 适配器的正常运行
- 文档周期性审计纳入 agenthub-phase-wrapup 标准流程
- CONTEXT.md 的 Phase 描述从五阶段更新为七阶段模型

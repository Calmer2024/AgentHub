# Phase 7: UX 体验闭环 + MVP 演示闭环 📋 PLANNED

**关联 ADR**: [ADR-0008](../../adr/0008-revised-development-strategy.md) §7
**关联 PRD**: [PRD-03: User Experience](../../PRD/03-User_Experience.md), [PRD-05: End-to-End Flow](../../PRD/05-End_to_End_Product_Flow.md)
**依赖**: Phase 4 (消息操作) + Phase 5 (产物管理) + Phase 6 (Workspace Runtime + CLI 适配器 + 产物入口桥接)
**状态**: 计划中

---

## 1. 全局定位

Phase 7 位于北极星链路的 **用户体验与演示闭环** 段：

```text
Workspace 绑定
  -> 用户输入
  -> Orchestrator/Agent 执行
  -> Artifact Card
  -> Artifact Drawer 预览
  -> 局部编辑/版本化
  -> Approval Card 审批继续
  -> 最终中枢总结
```

Phase 7 的目标不是“做一点 UI 打磨”，而是把 Phase 1-6 的能力串成可答辩、可演示、用户能理解的产品闭环。

---

## 2. 板块目标

实现 PRD-03 定义的完整用户体验：
- **动态三栏布局**：产品级的生产力工具界面
- **产物抽屉**：所见即所得的代码/网页预览
- **人工审批断点**：Human-in-the-loop 的关键交互
- **环境体检**：系统状态一目了然
- **MVP 演示脚本**：workspace 绑定后，输入任务并完成 Agent 输出、Artifact 预览、局部编辑、审批继续

---

## 3. 子模块

### Module 7A: 动态三栏布局 + 产物抽屉

| 维度 | 内容 |
|------|------|
| **Spec** | [02-artifact-drawer.md](02-artifact-drawer.md) |
| **范围** | 右区 Artifact Drawer (0→40-50% 宽度, 可拖拽), 抽屉内 [代码 Diff]/[网页预览] 双态, 资产卡片增强 |
| **前端** | `ArtifactDrawer.tsx`, `ArtifactCard.tsx` (增强), 布局容器重构 |

### Module 7B: 人工审批断点

| 维度 | 内容 |
|------|------|
| **Spec** | [03-approval-checkpoints.md](03-approval-checkpoints.md) |
| **范围** | `requires_human_approval` → PAUSED → 前端阻断卡片 + 确认/驳回按钮 + 输入框暂停遮罩 |
| **后端** | `POST /api/tasks/{id}/approve` (PRD-04 §3.1) |
| **前端** | `ApprovalCard.tsx` (红色警戒线 + 操作按钮) |

### Module 7C: 环境体检卡片

| 维度 | 内容 |
|------|------|
| **Spec** | [04-health-check.md](04-health-check.md) |
| **范围** | 左栏底部：检测 CLI 工具/运行时可用性 → 绿/红状态指示灯 |
| **后端** | `GET /api/system/health` (新增) |
| **前端** | `HealthCheckCard.tsx` |

### Module 7D: Store 拆分 + 全局 UX 打磨

| 维度 | 内容 |
|------|------|
| **Spec** | [01-integration.md](01-integration.md) |
| **范围** | Zustand store: chatStore/sessionStore/searchStore 独立文件; SessionList 搜索跳转; P0/P1 UX 缺陷清零; 全局回归 |
| **前端** | Store 文件拆分, UX polish |
| **测试** | 全量回归: backend + frontend + E2E |

---

## 4. 验收标准

- [ ] **7A-1**: 点击资产卡片 [预览产物] → 右区抽屉平滑滑出（默认 40% 宽度）
- [ ] **7A-2**: 抽屉左侧边缘可拖拽调整宽度（min 30%, max 60%）
- [ ] **7A-3**: 抽屉内 [网页预览] 模式 → IFrame 真实渲染 HTML
- [ ] **7A-4**: 抽屉内 [代码 Diff] 模式 → 文件树 + Monaco Editor 并排对比
- [ ] **7A-5**: 再次点击 [预览产物] 或点击抽屉外区域 → 抽屉收起
- [ ] **7B-1**: Orchestrator 任务 `requires_human_approval=true` → 完成时状态 PAUSED → 前端显示阻断卡片
- [ ] **7B-2**: 阻断卡片: 红色/橙色边框 + "架构设计已完成，请审批" + [确认] [驳回] 按钮
- [ ] **7B-3**: 点击 [确认] → 任务 COMPLETED → 自动触发下游依赖任务
- [ ] **7B-4**: 点击 [驳回] → 输入框可用 → 用户与 Agent 讨论修改 → 再次提交审批
- [ ] **7C-1**: 左栏底部环境体检卡片 → Claude Code/Node.js/Python 状态指示灯
- [ ] **7C-2**: 新会话创建时自动检测 → 缺失工具红字提示
- [ ] **7D-1**: chatStore/sessionStore/searchStore 独立文件，功能无回归
- [ ] **7D-2**: 搜索面板点击结果 → 切换会话 → 滚动到消息 → 闪烁高亮
- [ ] **7D-3**: 全量回归 (pytest + vitest + tsc --noEmit) 零失败
- [ ] **7E-1**: MVP 演示脚本跑通：workspace 绑定 → 输入任务 → Agent 输出 Artifact → 打开 Drawer → 编辑并确认新版本 → 审批继续 → 中枢总结

---

## 5. MVP 演示脚本

Phase 7 完成时必须能演示：

1. 新建协作任务：“做一个登录页，要求有邮箱、密码、提交按钮。”
2. 系统创建或绑定本机 workspace，并在会话中展示 workspace 状态。
3. Orchestrator 创建任务或选择 Agent，聊天流展示执行状态。
4. Agent 在 workspace 中执行，输出或文件变更被 Phase 6 桥接为 Artifact，聊天流出现 `LoginPage v1` 卡片。
5. 点击卡片打开右侧 Drawer，网页预览或代码 Diff 可见。
6. 点击“引用此版本”或在 Drawer 选中按钮代码，输入“把提交按钮改成红色”。
7. 系统生成 Diff 预览，用户确认后创建 `v2`。
8. 如果任务需要审批，Approval Card 打开当前 Artifact，用户确认后下游任务继续。
9. Orchestrator 输出最终总结，说明 workspace、产物、版本和后续可做事项。

---

## 6. 上下游契约

| 方向 | 契约 |
|------|------|
| 上游输入 | Phase 4 消息引用/搜索、Phase 5 Artifact API、Phase 6 workspace/preview 状态、`artifact.created` 与 CLI 事件 |
| 本阶段输出 | 产品级三栏 UI、Drawer 状态、ApprovalCard 操作、环境健康状态、端到端 E2E |
| 下游消费 | MVP 答辩演示、后续 P2 部署/多端扩展 |
| 未覆盖边界 | 部署发布、图片/附件上传、桌面端、移动端 |

---

## 7. 接口契约

### 新增 API

```
GET  /api/system/health    → 200 { "claude": "available", "node": "available", ... }
POST /api/tasks/{id}/approve → 200 { "status": "COMPLETED" }
POST /api/tasks/{id}/reject  → 200 { "status": "PENDING" }
```

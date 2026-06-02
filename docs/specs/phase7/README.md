# Phase 7: UX 体验闭环 + 集成收尾 📋 PLANNED

**关联 ADR**: [ADR-0008](../../adr/0008-revised-development-strategy.md) §7
**关联 PRD**: [PRD-03: User Experience](../../PRD/03-User_Experience.md)
**依赖**: Phase 4 (消息操作) + Phase 5 (产物管理) + Phase 6 (CLI 适配器)
**状态**: 计划中

---

## 1. 板块目标

实现 PRD-03 定义的完整用户体验：
- **动态三栏布局**：产品级的生产力工具界面
- **产物抽屉**：所见即所得的代码/网页预览
- **人工审批断点**：Human-in-the-loop 的关键交互
- **环境体检**：系统状态一目了然

---

## 2. 子模块

### Module 7A: 动态三栏布局 + 产物抽屉

| 维度 | 内容 |
|------|------|
| **范围** | 右区 Artifact Drawer (0→40-50% 宽度, 可拖拽), 抽屉内 [代码 Diff]/[网页预览] 双态, 资产卡片增强 |
| **前端** | `ArtifactDrawer.tsx`, `ArtifactCard.tsx` (增强), 布局容器重构 |

### Module 7B: 人工审批断点

| 维度 | 内容 |
|------|------|
| **范围** | `requires_human_approval` → PAUSED → 前端阻断卡片 + 确认/驳回按钮 + 输入框暂停遮罩 |
| **后端** | `POST /api/tasks/{id}/approve` (PRD-04 §3.1) |
| **前端** | `ApprovalCard.tsx` (红色警戒线 + 操作按钮) |

### Module 7C: 环境体检卡片

| 维度 | 内容 |
|------|------|
| **范围** | 左栏底部：检测 CLI 工具/运行时可用性 → 绿/红状态指示灯 |
| **后端** | `GET /api/system/health` (新增) |
| **前端** | `HealthCheckCard.tsx` |

### Module 7D: Store 拆分 + 全局 UX 打磨

| 维度 | 内容 |
|------|------|
| **范围** | Zustand store: chatStore/sessionStore/searchStore 独立文件; SessionList 搜索跳转; P0/P1 UX 缺陷清零; 全局回归 |
| **前端** | Store 文件拆分, UX polish |
| **测试** | 全量回归: backend + frontend + E2E |

---

## 3. 验收标准

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

---

## 4. 接口契约

### 新增 API

```
GET  /api/system/health    → 200 { "claude": "available", "node": "available", ... }
POST /api/tasks/{id}/approve → 200 { "status": "COMPLETED" }
POST /api/tasks/{id}/reject  → 200 { "status": "PENDING" }
```

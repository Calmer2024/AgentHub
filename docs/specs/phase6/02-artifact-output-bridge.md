# Spec: Phase 6F — Agent 输出到 Artifact 桥接

**版本**: v2.0
**更新日期**: 2026-06-04
**状态**: Draft
**关联 ADR/PRD**: [PRD-01](../../PRD/01-Architecture_Adapter.md) §3.4、[PRD-05](../../PRD/05-End_to_End_Product_Flow.md)、[ADR-0005](../../adr/0005-target-architecture.md) §接口契约
**依赖模块**: Phase 6A Workspace Runtime、Phase 6B-6E CLI Adapter、Phase 3 EventBus、Phase 5 ArtifactService

---

## 1. 目标

CLI Adapter 产出了 `agent.output` 和 `artifact_signal` 事件，但它们还不是数据库中的 Artifact 记录。本模块是这两者之间的桥——消费 Adapter 的输出信号和 workspace 文件变更，统一转换为 `artifact.detected` 事件，再由 ArtifactService 落库创建可预览、可编辑、可版本化的 Artifact，最终让聊天流中出现 Artifact Card。

**成功标准**（可证伪）：

- [ ] Claude Code 输出一个完整的 ` ```html ... ``` ` 代码块后，会话产物列表中出现一个 `web_preview` 类型的 Artifact，版本号为 v1
- [ ] Agent 在 workspace 中创建了 3 个文件、修改了 1 个文件 → workspace.diff_ready 触发 → 创建 1 个 `file_tree` Artifact，包含全部 4 个文件路径
- [ ] 不完整的代码块（未闭合的 ```）不会触发任何 Artifact 创建
- [ ] 置信度 0.5-0.8 的检测结果不会自动创建 Artifact，仅记录为候选事件
- [ ] Orchestrator 子任务带 `expected_outputs: [{ artifactType: "web_preview" }]` 时，Agent 输出的 HTML 代码块置信度阈值降低 0.2
- [ ] 不通过标准：Adapter 直接调用 ArtifactService 写库（绕过本模块的事件桥接）

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
CLI Adapter 输出 agent.output（含 artifact_signal）
  → [本模块] ArtifactDetectionService.inspect_agent_output()
  → 检测规则匹配 + 置信度计算
  → artifact.detected 事件
  → ArtifactService.create_from_detected_event()
  → Artifact 落库（session_id/message_id/task_id/project_id/version=1）
  → artifact.created 事件
  → 聊天流 Artifact Card
  → Phase 7 Drawer 预览
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | `agent.output`（含 artifact_signal chunk）、`workspace.diff_ready`、Orchestrator 子任务的 `expected_outputs` | 消费上游信号，执行检测规则 |
| **下游产出** | `artifact.detected` 事件（→ ArtifactService）、`artifact.created` 事件（→ 前端卡片 + Drawer） | 产出标准化产物事件 |
| **本模块不通** | 不直接渲染 Artifact Card UI（→ 前端消费 artifact.created）；不做 Drawer 交互（→ Phase 7）；不做产物编辑/版本化（→ Phase 5） | |

---

## 3. 跨模块契约

### 3.1 API 端点

本模块不直接暴露新 API。产物桥接在 Agent 消息完成后自动触发。涉及的现有端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/sessions/{id}/artifacts` | GET | Phase 5 已有 → 本模块产出的 Artifact 可通过此接口查询 |
| `/api/artifacts/{id}` | GET | Phase 5 已有 → 返回产物详情（含 file_path、preview_id） |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `artifact.detected` | ArtifactDetectionService → EventBus | `{ sessionId, messageId, taskId?, agentId, projectId, artifactType: "code_diff"\|"web_preview"\|"document"\|"file_tree", title, content, source: "cli_agent"\|"orchestrator"\|"workspace_diff", confidence: float, workspaceId?, filePath?, previewId? }` |
| `artifact.created` | ArtifactService → EventBus | `{ artifactId, sessionId, messageId, taskId?, projectId, version: 1, artifactType }` |
| `artifact.detection_failed` | ArtifactDetectionService → EventBus | `{ sessionId, messageId, reason, partialContent }` |

### 3.3 数据库 Schema 变更

```sql
-- 在现有 artifacts 表基础上补充字段
ALTER TABLE artifacts ADD COLUMN project_id VARCHAR REFERENCES projects(id);
ALTER TABLE artifacts ADD COLUMN file_path VARCHAR;
ALTER TABLE artifacts ADD COLUMN source VARCHAR DEFAULT 'api_agent';
ALTER TABLE artifacts ADD COLUMN confidence FLOAT;
ALTER TABLE artifacts ADD COLUMN task_id VARCHAR;
```

### 3.4 跨组件 TypeScript 类型

```typescript
type ArtifactType = 'code_diff' | 'web_preview' | 'document' | 'file_tree';

interface ArtifactDetectedPayload {
  sessionId: string;
  messageId: string;
  taskId?: string;
  agentId: string;
  projectId: string;
  artifactType: ArtifactType;
  title: string;
  content: string;
  source: 'cli_agent' | 'orchestrator' | 'workspace_diff';
  confidence: number;
  workspaceId?: string;
  filePath?: string;
}

interface ExpectedOutput {
  type: 'artifact';
  artifactType: ArtifactType;
  titleHint?: string;
}
```

---

## 4. 行为规格

### 4.1 检测规则

| 输入信号 | artifact_type | 检测条件 | 置信度基值 |
|---------|--------------|---------|-----------|
| fenced code block: `html` | `web_preview` | 内容含 `<html`、`<body`、`<!DOCTYPE` 或 `<div` + 闭合标签 | 0.85 |
| fenced code block: `tsx`/`jsx`/`vue`/`svelte` | `web_preview` | 内容含 `export default` 或 `function` + JSX return | 0.80 |
| fenced code block: `diff`/`patch` | `code_diff` | 内容含 `@@ -` 或 `--- a/` `+++ b/` | 0.90 |
| CLI 文件变更摘要 | `file_tree` | 内容含 `Created:`/`Modified:`/`Deleted:` + 有效文件路径 | 0.85 |
| 代码块内的结构化 Markdown | `document` | expected_outputs 指定 document 类型，或文本 > 500 字符 + 含 h1/h2 标题 | 0.70 |

### 4.2 置信度决策

| 置信度 | 行为 |
|--------|------|
| ≥ 0.80 | 自动创建 Artifact（artifact.detected → ArtifactService 直接落库） |
| 0.50 – 0.79 | 仅发 artifact.detected 候选事件，不自动落库（Phase 7 可增加用户确认 UI） |
| < 0.50 | 作为普通文本消息保留，不触发任何 Artifact 流程 |

Orchestrator 子任务携带 `expected_outputs` 时，对应 `artifactType` 的检测阈值降低 0.20。

### 4.3 正常流程

```
1. CLI Adapter 完成执行 → agent.process.completed
2. ChatService 聚合完整 Agent 输出文本
3. ArtifactDetectionService.inspect_agent_output(text, expected_outputs)
   a. 扫描所有 fenced code block
   b. 对每个 block 匹配检测规则 → 计算 artifactType + confidence
   c. 应用 expected_outputs 加权（如匹配 → confidence += 0.20）
   d. 生成 0-N 个 ArtifactDetectedEvent
4. 对每个 confidence >= 0.80 的事件:
   a. ArtifactService.create_from_detected_event()
   b. 创建 Artifact 记录（version=1, source, confidence, project_id, file_path）
   c. 发布 artifact.created
5. 前端收到 artifact.created → 在聊天流 Agent 消息下方插入 Artifact Card
```

### 4.4 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态** | 聊天流中只有文本消息，无 Artifact Card | Agent 回复不含代码/产物 |
| **加载态** | Agent 消息完成后，消息气泡下方短暂显示 "🔍 正在分析产物..." spinner（< 1 秒） | 检测服务正在扫描 |
| **正常态** | Agent 消息下方出现 Artifact Card，卡片标题 + 类型图标 + [👀 预览] + [💬 引用] 按钮 | 检测到产物 + 落库成功 |
| **完成态** | 卡片上的版本号显示 v1（首次创建）或 v{n}（重新生成）；Drawer 打开后可预览/编辑 | 产物版本链建立 |
| **错误态** | 见 §4.5 | |
| **边界态** | 一条 Agent 消息包含 4 个代码块（2 个 html + 1 个 diff + 1 个 python）→ 创建 3 个 Artifact Card（html × 2 + diff × 1），python 代码块作为文本保留；超大代码块（> 500KB）→ 创建 status='oversized' 的 Artifact，卡片显示"内容过大，无法预览" | |

### 4.5 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| 代码块未闭合（只有 ` ```html` 无闭合标记） | — | 无操作（不创建 Artifact，文本保留原样） | — |
| Artifact 落库失败（DB 写入错误） | — | Agent 文本消息正常显示；卡片区域显示 "⚠️ 产物创建失败，请重试" | 重新生成 Agent 回复 |
| 内容超过大小限制（> 1MB） | — | 创建 status='oversized' 的 Artifact；卡片显示"📦 内容过大（{size}），无法在线预览" + [⬇ 下载] 按钮 | 下载到本地查看 |
| 重复检测（同一 message_id 多次触发） | — | 幂等处理，不创建重复 Artifact | — |
| expected_outputs 包含未知 artifactType | — | 忽略该条 expected_output，按正常规则检测 | — |

---

## 5. 前端交互序列

### 5.1 Artifact Card 出现

```
SSE: agent.process.completed
  → 前端: Agent 消息气泡完成 → 气泡下方出现 1 秒 spinner "🔍 正在分析产物..."
  → EventBus → ArtifactDetectionService → ArtifactService
  → SSE: artifact.created { artifactId, artifactType: "web_preview", title: "登录页面", version: 1 }
  → 前端: spinner 消失 → Agent 消息下方插入 ArtifactCard 组件
    - 左侧: 类型图标（🌐 web_preview / 📝 code_diff / 📁 file_tree / 📄 document）
    - 中间: 加粗标题 "登录页面"
    - 右侧: [👀 预览] [💬 引用] 两个按钮
    - 底部: 灰色小字 "v1 · 刚刚 · Claude Code"
  → 前端: chatStore.artifacts 更新 → 会话产物列表同步刷新
```

### 5.2 多产物卡片

```
（同一条 Agent 消息产出了 html 代码块和 diff 代码块）
  → SSE: artifact.created { artifactId: "art_1", artifactType: "web_preview", title: "登录页面" }
  → SSE: artifact.created { artifactId: "art_2", artifactType: "code_diff", title: "修改 App.tsx" }
  → 前端: Agent 消息下方出现两个 ArtifactCard（垂直排列，按创建时间排序）
```

### 5.3 产物与 Drawer 联动

```
用户: 在聊天流中点击 ArtifactCard 的 [👀 预览] 按钮
  → 前端: artifactType 判断
    - web_preview: 打开 Drawer → iframe 展示 previewUrl（来自 /api/projects/{id}/preview）
    - code_diff: 打开 Drawer → DiffViewer 组件（split 模式）展示 diff 内容
    - file_tree: 打开 Drawer → FileTreeViewer 展示文件列表
  → Drawer: 顶部显示产物标题 + 版本切换下拉 → 内容区展示预览/Diff
```

---

## 6. 验收标准

- [ ] AC-01: Claude Code 输出完整 ` ```html <html>...</html> ``` ` → artifact.detected（web_preview, confidence ≥ 0.80）→ artifact.created → 前端 Artifact Card 出现
- [ ] AC-02: Codex 输出 ` ```diff @@ -10,6 +10,8 @@ ``` ` → artifact.detected（code_diff, confidence ≥ 0.80）→ artifact.created
- [ ] AC-03: `workspace.diff_ready` 事件携带 3 个 changed 文件 → 创建 file_tree Artifact，内容包含全部 3 个路径
- [ ] AC-04: 代码块未闭合 → 不触发任何 artifact.detected
- [ ] AC-05: confidence 0.65 的检测 → 仅 artifact.detected 候选，不落库
- [ ] AC-06: Orchestrator 传 `expected_outputs: [{ artifactType: "web_preview" }]` → 同类型检测阈值降低 0.20 → 原 0.65 的 HTML 块变为 0.85 → 自动落库
- [ ] AC-07: 同一 message 包含 2 个 html 代码块 → 创建 2 个独立 Artifact（标题自动加序号）
- [ ] AC-08: Artifact Card 绑定 `artifactId / messageId / taskId / projectId / version` — 全部字段非空且正确
- [ ] AC-09: 创建出的 Artifact 可直接通过 Phase 5 API 查看版本历史、生成 Diff、在线编辑
- [ ] AC-10: Artifact 落库失败 → Agent 文本消息不受影响 → 不阻断聊天流

---

## 7. 测试策略

### 7.1 单元测试 (18 条)

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| 代码块检测 | 6 | html/tsx/diff/python/未闭合/多块 |
| 置信度计算 | 4 | 基准值/expected_outputs 加权/边界/降级 |
| workspace diff 检测 | 3 | 单文件/多文件/无变更 |
| 幂等性 | 2 | 重复调用/相同 message_id |
| ArtifactService 集成 | 3 | create_from_detected_event/落库/事件发布 |

### 7.2 集成测试

- 测试 CLI fixture 输出完整 HTML → 验证 artifact.detected → artifact.created 全链路
- Mock workspace.diff_ready 事件 → 验证 file_tree Artifact 创建
- Mock 低置信度检测 → 验证候选事件不落库

### 7.3 E2E 测试

- 真实浏览器：Claude Code Agent 输出 HTML → 聊天流 Artifact Card 出现 → 点击预览 → Drawer iframe 展示网页

---

## 8. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| Adapter 不直接写数据库，只上报事件 | PRD-01 §3.4 + ADR-0005 §接口契约 |
| Artifact 创建由 ArtifactService 统一负责 | PRD-05 §4 |
| Agent 输出通过事件驱动流转，不跨模块直接调用 | ADR-0005 §依赖规则 2 |
| 产物类型枚举（code_diff/web_preview/document/file_tree） | PRD-03 §3.3-3.4 |
| 置信度分层决策（自动落库 vs 候选 vs 忽略） | PRD-05 §4 产物创建规则 |

---

## 9. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 6A WorkspaceService | `workspace.diff_ready` 事件、Project 文件读取 / snapshot diff / static preview | ✅ 已验收 |
| Phase 6B-6E CLI Adapter | `agent.output`（含 artifact_signal chunk）| ❌ 本 Phase 同步开发 |
| Phase 3 EventBus | `publish() / subscribe()` | ✅ 已就绪 |
| Phase 5 ArtifactService | `create_from_detected_event()`、版本链 API | ✅ 已就绪（需扩展方法） |

---

## 10. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不做 Artifact Card 的 UI 渲染逻辑 | 前端组件职责 | 前端 ArtifactCard 组件 |
| 不做 Drawer 预览交互 | 下游链路 | Phase 7 |
| 不做 Artifact 的编辑/版本化 | 已有能力 | Phase 5（已就绪） |
| 不解析图片/二进制文件 | 超出范围 | — |
| 不做自然语言 → Artifact 的意图识别 | Orchestrator 职责 | Phase 3 Orchestrator |
| Adapter 不直接调 ArtifactService | 架构约束 | 本模块统一桥接 |

---

## 11. 破坏性变更与迁移

本模块为全新模块，不涉及对已有 Artifact 记录的破坏性变更。已有 `artifacts` 表新增列（project_id、file_path、source、confidence、task_id）均为 NULLABLE，不破坏已有数据。

> **版本历史**
> - v1.0 (2026-06-03): 初始版本
> - v2.0 (2026-06-04): 按新 Spec 模板全面重构
> - v2.1 (2026-06-04): 同步 Phase 6A 已验收状态；Artifact Bridge 后续可消费 `workspace.diff_ready` 与 Project 文件读取能力

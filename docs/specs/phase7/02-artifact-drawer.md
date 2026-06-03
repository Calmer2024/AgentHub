# Spec: Phase 7A — 动态三栏布局 + Artifact Drawer

**版本**: v1.0  
**创建日期**: 2026-06-03  
**状态**: Draft  
**关联**: [PRD-03](../../PRD/03-User_Experience.md) §3.3-3.4, [PRD-05](../../PRD/05-End_to_End_Product_Flow.md)  
**依赖**: Phase 5 Artifact API, Phase 6 `artifact.created` 事件

---

## 1. 目标

把聊天流中的 Artifact Card、左侧产物列表、审批卡片统一接入右侧 Artifact Drawer。用户能在同一界面完成预览、版本切换、Diff 查看、引用版本、局部编辑。

---

## 2. 全局链路定位

```text
artifact.created
  -> Artifact Card
  -> Artifact Drawer
  -> 版本/Diff/预览
  -> 引用或局部编辑
  -> Phase 5 创建新版本
```

| 问题 | 回答 |
|------|------|
| 上游 | `artifact.created` 事件、`GET /api/sessions/{id}/artifacts`、Artifact Card 点击 |
| 下游 | Drawer 打开状态、版本选择、编辑请求、引用标签 |
| 用户可完成任务 | 在不离开聊天的情况下预览产物、比较版本、发起修改 |
| 不打通 | 部署发布、真实文件树 IDE 编辑、多端适配 |

---

## 3. 前端组件

```text
AppShell
  ├─ Sidebar
  ├─ ChatWorkspace
  │   ├─ ChatWindow
  │   └─ ChatInput
  └─ ArtifactDrawer
      ├─ DrawerToolbar
      ├─ ArtifactVersionSelector
      ├─ ArtifactPreviewPane
      ├─ DiffViewer
      └─ CodeSelector
```

### 3.1 Drawer 状态

```typescript
interface ArtifactDrawerState {
  isOpen: boolean;
  artifactId: string | null;
  activeVersion: number | null;
  mode: "preview" | "diff" | "code";
  widthPercent: number; // 30-60, default 42
  referencedFrom?: "card" | "sidebar" | "approval";
}
```

### 3.2 打开入口

| 入口 | 行为 |
|------|------|
| Artifact Card `[预览产物]` | 打开 Drawer，加载该 Artifact 最新版本 |
| 左侧产物列表 | 打开 Drawer，加载该 Artifact 最新版本 |
| Approval Card 主区域 | 打开 Drawer，加载待审批任务关联 Artifact |
| 搜索结果中的产物卡片 | 切换会话后打开 Drawer |

---

## 4. 行为规格

### 4.1 正常流程

1. 前端收到 `artifact.created` 或加载会话产物列表。
2. 聊天流渲染 Artifact Card，卡片显示类型、标题、版本、状态。
3. 用户点击预览。
4. Drawer 从右侧滑出，默认宽度 42%，中区聊天被压缩但保持可读。
5. Drawer 调用 `GET /api/artifacts/{id}/content` 和 `GET /api/artifacts/{id}/versions`。
6. 用户切换 `预览 / Diff / 代码` 模式。
7. 用户点击“引用此版本”，ChatInput 上方出现引用标签。
8. 用户选中代码并提交修改，调用 Phase 5 edit API，展示 Diff 预览。
9. 用户确认后 Drawer 切换到新版本，聊天流追加新版本卡片。

### 4.2 异常流程

| 场景 | 预期行为 |
|------|----------|
| Artifact 加载失败 | Drawer 保持打开，显示错误和重试按钮 |
| 预览 HTML 不可渲染 | 自动切到代码模式 |
| Diff API 失败 | Diff 区域显示错误，不影响预览模式 |
| 版本链为空 | 显示当前版本，不显示版本下拉 |
| Drawer 宽度过窄 | 自动隐藏次要文字，只保留图标和 tooltip |

---

## 5. 验收标准

- [ ] Artifact Card、左侧产物列表、Approval Card 都能打开同一个 Drawer。
- [ ] Drawer 宽度可拖拽，范围 30%-60%，刷新页面后保留上次宽度。
- [ ] 预览模式能渲染 HTML Artifact；代码模式能显示源码。
- [ ] Diff 模式能选择两个版本并展示差异。
- [ ] 点击“引用此版本”后，下一条聊天消息携带 `referenced_artifact_id` 和 `referenced_artifact_version`。
- [ ] 选中代码并确认修改后，创建新版本并自动切到新版本。
- [ ] 移动端宽度下 Drawer 变为全屏覆盖层，不遮挡输入框。

---

## 6. 测试

- Component: Drawer 打开/关闭、模式切换、宽度拖拽、版本切换。
- API mock: content/versions/diff/edit 成功与失败。
- E2E: Artifact Card -> Drawer -> edit -> new version。

---

## 7. Non-Goals

- 不实现 VS Code 级完整 IDE。
- 不实现部署按钮。
- 不实现多文件复杂项目的深度浏览器，`file_tree` 仅做只读展示。

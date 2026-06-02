# Spec: Phase 5A — 产物版本 + Diff

**版本**: v2.0
**创建日期**: 2026-05-28 (v1.0), 2026-06-02 (v2.0 重组)
**状态**: Draft
**关联**: [PRD-03: User Experience](../../PRD/03-User_Experience.md) §3.3-3.4, [PRD-04: Data & API](../../PRD/04-Data_API_Contracts.md) §3.3
**依赖**: Phase 3 (Artifact 模型: version, parent_artifact_id)

## 1. API

```
GET  /api/artifacts/{id}/versions   → 200 [{ version, content, created_at }, ...]
GET  /api/artifacts/{id}/diff?v1=1&v2=2 → 200 { from_version, to_version, diff }
```

## 2. 后端: ArtifactService

```python
class ArtifactService:
    async def create_version(self, artifact_id, content) -> ArtifactRead:
        """重新生成创建新版本：version += 1, parent_artifact_id → 旧版"""
        ...

    async def get_versions(self, artifact_id) -> list[ArtifactVersion]:
        """递归追溯 parent_artifact_id 构建版本链"""
        ...

    async def get_diff(self, artifact_id, v1, v2) -> DiffResult:
        """用 difflib.unified_diff 生成 diff"""
        ...
```

### 版本链模型

```
Artifact V1 (parent=null)
  └─ Artifact V2 (parent=V1)  ← regenerate 创建
       └─ Artifact V3 (parent=V2)
```

每次重新生成 → `version += 1`, `parent_artifact_id` 指向前版。

## 3. 前端

### VersionHistory.tsx
- 产物卡片上的版本下拉选择器
- 选项: "v1 (原始)", "v2 (重新生成)", "v3 (重新生成)"

### DiffViewer.tsx
- 使用 `react-diff-viewer-continued` (~15KB)
- 支持 split (左右对比) 和 unified (上下对比) 模式
- 增删行: 绿色/红色高亮

## 4. 验收标准

- [ ] 产物有多个版本 → 版本下拉切换查看历史版本
- [ ] 两版本 Diff 正确高亮增删行
- [ ] 切换版本时 Diff 视图实时更新

## 5. 新依赖

```
npm install react-diff-viewer-continued
```

## 6. 测试

- API: 版本链构建、Diff 生成、不存在的版本
- 前端: VersionHistory 渲染、DiffViewer split/unified
- 目标: 18 条

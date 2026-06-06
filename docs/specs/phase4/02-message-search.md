# Spec: Phase 4B — 消息搜索

**版本**: v2.0
**创建日期**: 2026-05-28 (v1.0), 2026-06-02 (v2.0 重组)
**状态**: Completed
**完成日期**: 2026-06-02
**关联**: [PRD-04: Data & API](../../PRD/04-Data_API_Contracts.md) §4 (全文检索 FTS5)
**依赖**: Phase 3 (FTS5 虚拟表 + 触发器已在迁移中创建)

## 1. API

```
GET /api/messages/search?session_id={id}&q=关键词&limit=20
→ 200 [{ id, content, highlight, role, agent_name, created_at }, ...]
```

## 2. 后端

### FTS5 查询 + LIKE fallback

```python
# MessageService
async def search_messages(session_id, query, limit=20) -> list[MessageRead]:
    try:
        # FTS5 全文搜索
        results = await db.execute(text(
            "SELECT m.*, snippet(messages_fts, 1, '<mark>', '</mark>', '...', 40)"
            " FROM messages m JOIN messages_fts fts ON m.rowid = fts.rowid"
            " WHERE messages_fts MATCH :q AND m.session_id = :sid"
        ), {"q": query, "sid": session_id})
    except OperationalError:
        # FTS5 查询失败 → LIKE fallback
        results = await db.execute(
            select(Message).where(Message.session_id == session_id,
                                  Message.content.like(f"%{query}%"))
        )
```

实际实现还会在 FTS5 返回空结果时尝试 LIKE fallback，以保证中文关键词在 `unicode61` 分词边界下仍可检索。

## 3. 前端: SearchPanel.tsx

- 快捷键 `Ctrl+K` / `Cmd+K` 打开
- 搜索框 + 结果列表 (匹配片段 + 高亮 + 角色标签 + 时间)
- 点击结果项 → 滚动到对应消息位置 + 高亮闪烁 2s
- 空结果 → "未找到匹配消息"

## 4. 验收标准

- [x] 输入关键词 → 匹配结果显示高亮片段
- [x] 点击结果 → 跳转到对应消息并闪烁
- [x] FTS5 异常/空结果 → LIKE fallback 仍可用
- [x] 快捷键 Ctrl+K 打开搜索面板

## 5. 测试

- API: FTS5 搜索、LIKE fallback、空结果
- 前端: SearchPanel 渲染、结果列表、点击跳转
- 已覆盖: `test_messages_phase4.py`, `test_phase4_acceptance.py`, `SearchPanel.test.tsx`
- 真实验收: `e2e/phase4_real_acceptance.py`

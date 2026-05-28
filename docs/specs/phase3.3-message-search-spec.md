# Spec: Phase 3.3 — 消息搜索

**版本**: v1.0 | **状态**: Draft
**关联**: [Phase 3 Spec](phase3-enhancements-spec.md) §5.3.4
**依赖**: Module 1 (FTS5 虚拟表 + 触发器)
**可并行**: ✅ 与 Module 2

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

## 3. 前端: SearchPanel.tsx

- 快捷键 `Ctrl+K` / `Cmd+K` 打开
- 搜索框 + 结果列表 (匹配片段 + 高亮 + 角色标签 + 时间)
- 点击结果项 → 滚动到对应消息位置 + 高亮闪烁 2s
- 空结果 → "未找到匹配消息"

## 4. 验收标准

- [ ] 输入关键词 → 匹配结果显示高亮片段
- [ ] 点击结果 → 跳转到对应消息并闪烁
- [ ] FTS5 异常 → LIKE fallback 仍可用
- [ ] 快捷键 Ctrl+K 打开搜索面板

## 5. 测试

- API: FTS5 搜索、LIKE fallback、空结果
- 前端: SearchPanel 渲染、结果列表、点击跳转
- 目标: 10 条

# Architecture 文档索引

> 本目录保存 AgentHub 当前系统事实。  
> 如果要了解关键架构决策、核心设计和开发约束，请读 `docs/adr/`；如果要了解“现在系统实际是什么样”，请读本目录。

## 文档列表

| 文档 | 内容 |
| --- | --- |
| [overview.md](overview.md) | 当前架构总览、分层结构、主请求链路和本机/云端分流 |
| [data-model.md](data-model.md) | 当前数据库表组、核心关系、FTS 表和数据设计约束 |
| [runtime-model.md](runtime-model.md) | 本机 CLI runtime、云端 runtime、Run/Task/Process 状态和审批 |
| [event-contracts.md](event-contracts.md) | SSE、WebSocket、EventBus 事件类型和新增事件规则 |

## 使用建议

- 答辩前快速掌握架构：先读 `overview.md`，再读 `data-model.md`。
- 排查运行状态问题：读 `runtime-model.md`。
- 新增 SSE / WebSocket / EventBus 事件：先读 `event-contracts.md`。
- 判断某类信息应该写到哪里：读 [../documentation-governance.md](../documentation-governance.md)。

## 更新规则

当代码中的当前事实发生变化时，同步更新本目录。典型场景：

- 新增或删除核心表。
- 改变 Project / Session / Agent / Artifact / Runtime 的关系。
- 新增 runtime 状态或事件类型。
- 改变本机/云端执行链路。

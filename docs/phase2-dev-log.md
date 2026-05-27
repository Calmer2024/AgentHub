# Phase 2 开发日志：核心功能

## 1. 阶段概述

| 模块 | 内容 | 规模 |
|------|------|------|
| Module 1: Agent 管理 | AgentConfig CRUD + Provider 配置 (6厂商) + SettingsPanel | 18 files, ~2000 LOC |
| Module 2: WebSocket | ConnectionManager + WS 端点 + 心跳/重连 + chat 集成 | 5 files, ~250 LOC |
| Module 3: 群聊 + Orchestrator | SessionMember + Orchestrator + GroupChatCreator + @提及 | 12 files, ~800 LOC |
| Module 4: 产物预览 | Artifact 模型 + Markdown 渲染 + ArtifactCard | 6 files, ~400 LOC |

**Spec 验收标准**: 7/7 通过  
**测试**: 46 passed (39 backend + 7 frontend)  
**架构**: Provider → AgentConfig → Session 三层 + Domain/Orchestrator 域层

## 2. 开发时间线

### Day 1-2: Module 1 起步
- AgentConfig 模型 + CRUD API
- 前端 AgentPanel + SettingsPanel
- 首次遇到 camelCase/snake_case 不一致问题

### Day 3-5: 架构修正
- 发现"Agent 管理"实则"Provider 配置"——重构为 AgentConfig 三层架构
- 新增 GLM/MiniMax 适配器，切换为官方 SDK
- 每个会话独立 Agent（非全局共享）

### Day 6-7: Module 2 WebSocket
- ConnectionManager + WS /ws/sessions/{id}
- 流式 token 实时推送，心跳 30s
- 前端 WSClient + 指数退避重连

### Day 8-9: Module 3 群聊
- SessionMember + Orchestrator + GroupChatCreator
- @提及智能补全 + 键盘导航
- 每个 Agent 独立消息气泡（agent.start 事件 → 按 agentId 路由 token）

### Day 10: Module 4 产物 + Markdown
- react-markdown + react-syntax-highlighter (oneDark)
- Artifact 模型 + ArtifactCard 组件
- 会话管理（删除/重命名/AI 总结标题）

## 3. 关键 Bug 与解决方案

### Bug 1: camelCase/snake_case 不匹配
- **现象**: 前端 API 调用 Setting/Agent 全部失败，字段读不到
- **根因**: Pydantic v2 默认忽略未知字段，前端 camelCase 被静默丢弃
- **解决**: 所有 Pydantic 模型加 `Field(alias="camelCase")` + `populate_by_name=True`
- **教训**: 前后端字段命名一致性必须在项目启动时约定，后补成本高

### Bug 2: 测试污染真实 .env
- **现象**: 运行测试后 .env 中的真实 API Key 被覆盖为 `sk-test-key-...`
- **根因**: `PUT /api/settings` → `_write_env()` 直接写真实文件
- **解决**: conftest `autouse=True` fixture mock `_write_env`

### Bug 3: 群聊 token 互相覆盖
- **现象**: @两个 Agent 的回复只显示最后一个 Agent 的输出
- **根因**: 多 Agent token 交错发给同一个 `appendStreamingToken`，写入同一个气泡
- **解决**: `agent.start` 事件 → 为每个 Agent 创建独立 placeholder → `appendAgentStreamingToken` 按 agentId 路由

### Bug 4: Orchestrator 依赖 SQLAlchemy
- **现象**: 代码审查发现 Domain 层违反 ADR-0005 "零框架依赖" 规则
- **根因**: `orchestrator.py` 直接 import `sqlalchemy`
- **解决**: DB 查询移到 chat.py API 层，Orchestrator.route() 接收预查询数据

## 4. 建立的基础设施

- AgentConfig 三层架构（Provider → Agent → Session）
- WebSocket 连接管理 + 心跳重连框架
- Orchestrator 域对象（纯逻辑，无框架依赖）
- Markdown 渲染管线（react-markdown + remark-gfm + syntax-highlighter）
- @提及智能补全系统

## 5. 关键方法总结

- **架构先行，代码后行**: Module 1 初期没有 AgentConfig 概念导致大量返工
- **小 commit 频繁提交**: 每次函数完成即 commit，共 ~30 个 commit
- **人工验收闸门**: Git 提交前必须用户确认，避免了多次错误提交
- **主动发现问题**: 从代码审查延申修复关联问题

## 6. 下一步

Phase 3: 增强特性 —— Agent 间自动对话、Orchestrator 智能路由、部署、跨平台

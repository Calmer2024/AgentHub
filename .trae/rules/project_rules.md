# AgentHub 项目规则

## AI 协作规则（最高优先级）

### 三层协作体系
本项目采用 Rules → Spec → Skill 三层 AI 协作体系（见 ADR-0007）：

1. **Rules（本文件 + CLAUDE.md）**：始终生效的全局约束，AI 每次对话自动加载
2. **Spec（docs/specs/）**：每个功能模块的详细规格，开发前必须让 AI 阅读对应 Spec
3. **Skill（.claude/skills/）**：可重复调用的开发工作流，封装标准化流程

### AI 协作铁律
- **无 Spec 不开发**：没有对应 Spec 文档的模块，AI 应拒绝开始写代码
- **契约优先**：先定义接口（抽象类/类型），再写实现。接口定了就不能随便改
- **按需引入架构层**：只在触发条件满足时才引入新架构层（见 ADR-0004），禁止提前建"可能以后用"的抽象
- **每个增量可演示**：一个增量结束时，必须是前端可操作、效果可见的完整状态

## Vibe Coding 核心约定

1. **架构打底优先**：正式写功能代码前，先完成顶层架构设计
2. **模块逐个突破**：完成一个模块后，立即写该模块的单元测试
3. **小步提交原则**：每完成一个能跑的小功能就立刻 commit
4. **单文件上限 300 行**：避免写出怪物文件，长了就拆分
5. **每日快照**：每天工作结束前 commit 标注"今日快照"

## 技术栈约束（锁定，不可变更）

- 前端：React + TypeScript + Vite + shadcn/ui + Tailwind CSS v3
- 后端：Python FastAPI + SQLAlchemy 2.0 + SQLite (aiosqlite)
- 桌面端：Tauri v2
- 移动端：Capacitor
- AI SDK：anthropic (Python), @anthropic-ai/sdk (TypeScript)

## 架构约束

- 只能向下依赖：上层可依赖下层，下层绝不依赖上层
- 同层不互依赖：同一层模块通过 Event Bus 或接口通信
- Domain 层零框架依赖：Orchestrator、ContextManager 不 import FastAPI/SQLAlchemy
- 环境变量管理所有密钥：API Key、数据库路径等通过 `.env` 注入，绝不硬编码

## 代码风格

- 所有注释和文档统一使用中文
- Python：所有函数 `async def`，完整类型注解
- TypeScript：禁止 `any` 类型，Zustand 管理全局状态
- API 路由：必须校验输入（空消息 → 400，不存在资源 → 404）
- 优先跑通功能，再逐步优化细节

## 当前开发阶段

**Phase 1: Walking Skeleton（行走骨架）**
- 范围：单聊全链路（前端 → API → Claude → SQLite）
- 不在范围：群聊、Orchestrator、WebSocket、产物预览、多 Agent、认证
- 验收标准：见 `docs/specs/phase1-skeleton-spec.md` 第 4 节
- 完成标志：5 条 AC 全部通过

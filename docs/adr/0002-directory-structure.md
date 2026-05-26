# ADR-0002: 项目目录结构规范

**Date**: 2026-05-25  
**Status**: Accepted

## Context
为了支持高效的 vibe coding，避免代码混乱，需要在项目开始前约定清晰的目录结构。

## Decision
采用前后端完全分离的独立目录结构：

```
AgentHub/
├── frontend/              # React 前端（Vite）
│   ├── src/
│   │   ├── components/    # shadcn/ui 组件 + 业务组件
│   │   ├── pages/         # 页面路由
│   │   ├── stores/        # 状态管理
│   │   └── api/           # 后端接口调用
│   └── package.json
├── backend/               # Python FastAPI 后端
│   ├── app/
│   │   ├── api/           # API 路由
│   │   ├── agents/        # Agent 适配器层
│   │   ├── models/        # SQLAlchemy 数据模型
│   │   └── core/          # 核心配置
│   └── requirements.txt
├── docs/
│   └── adr/               # ADR 记录
└── CONTEXT.md
```

## Consequences
- 前后端完全解耦，各自独立开发互不干扰
- vibe coding 时切换前端/后端的上下文成本极低
- 新人加入项目能一眼看懂结构

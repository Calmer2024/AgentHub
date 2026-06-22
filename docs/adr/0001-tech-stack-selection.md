# ADR-0001: 技术栈选型

**日期**: 2026-05-25
**状态**: Accepted

## 背景
项目需要全程使用 vibe coding 快速开发，同时满足多端支持（Web端、桌面端、移动端）的要求，用户已有 React + Python FastAPI 技术背景。

## 决策
选择以下技术栈：

| 层级 | 选型 |
|------|------|
| 前端 | React + TypeScript + Vite |
| 后端 | Python FastAPI + WebSocket |
| 桌面端 | Tauri v2（复用前端代码打包） |
| 移动端 | Capacitor（复用前端代码打包） |
| 数据库 | SQLite + SQLAlchemy 2.0 |
| UI | shadcn/ui + Tailwind CSS v3 |

## 影响
- 一套 React 代码库同时支持 Web、桌面端、移动端
- Python FastAPI 天然适配 LLM Agent 生态，接入各种 SDK 极其方便
- SQLite 零配置，无需额外数据库服务，vibe coding 启动速度极快

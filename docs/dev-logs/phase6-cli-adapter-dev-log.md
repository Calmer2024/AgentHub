# Phase 6 CLI Adapter 阶段开发日志

**日期**: 2026-06-05
**阶段**: Phase 6B-6E CLI Adapter 稳定化
**状态**: 实现基线已提交

## 1. 本阶段已完成

- 清理旧版本 API 伪 Agent 的活动路径：旧 provider adapter、provider/settings API、默认角色助手、用户可见模型综合配置面板均退出主流程。
- 保留 DeepSeek 作为内部系统模型，用于标题生成、群聊最终总结等产品内部能力，不作为用户 Agent 好友暴露。
- 种子化并规范化三个内置 CLI 好友：Claude Code、Codex、OpenCode。
- 新增 CLI-only 迁移，包括 executable/init args/env vars 字段，以及清理历史 agent config 记录。
- 实现真实 subprocess runtime：支持本机 CLI 执行、workspace cwd 绑定、stdout/stderr 流式读取、Windows 命令解析、进程注册表、超时处理和交互式回复。
- 按职责拆分 CLI runtime、默认配置、per-CLI adapter、输出解析、执行轨迹、Codex 配置检测和聊天流服务。
- 为 Claude Code、Codex、OpenCode 实现专属 adapter。
- 单聊和群聊/Orchestrator 路径在 session 绑定 Project workspace 时统一接入 CLI runner。
- 在回复气泡下方新增结构化执行轨迹，并将其持久化到 message metadata。
- 优化前端聊天 UI：Telegram 风格气泡、Agent 头像、Markdown 阅读体验、滚动行为、引用/搜索/操作、执行流程块独立滚动。
- 用 CLI Agent 设置弹窗替换旧模型设置面板。
- 通过 AgentHub UI 支持 Codex 官方 OpenAI 与第三方中转配置。
- 新增本机 Codex 配置修复：API Key 写入 `CODEX_HOME/.env`；`config.toml` provider 使用 command-backed auth helper 从 `.env` 按需读取；中转模式不再依赖易变的 ChatGPT token，也不要求用户配置全局 `CODEX_API_KEY`。
- 对 Codex HTML 错误页、模型列表碎片和已知 stderr 噪声做过滤和提示。
- 接通 OpenCode 真实 CLI 路径，修复早期 prompt/参数导致“进程已结束但气泡仍等待回复”的问题。
- 增加项目重命名/删除能力，并调整项目/会话创建入口位置。

## 2. 验证状态

本阶段已验证：

- 真实 Claude Code API 路径可创建 Project、Session，并通过 AgentHub chat 在 workspace 写入目标文件。
- OpenCode 真实 CLI 路径经过人工验收，通过参数规范化和消息完成处理修复了等待回复问题。
- Codex 在通过 AgentHub 配置中转 API Key 并修复本机 Codex 配置后可用。
- 本轮提交前已运行：

```powershell
cd backend && .\venv\Scripts\python.exe -m pytest test_api/ test_unit/ test_smoke.py -q
cd frontend && npm run build
cd frontend && npx vitest run
```

结果：

- 后端测试：220 passed；
- 前端构建：通过，存在 Vite chunk 体积警告；
- 前端测试：39 passed。

## 3. 关键决策

- 用户可见 Agent 是 CLI wrapper，不是角色 prompt，也不是 API provider。
- 一个 Project 拥有一个本机 workspace；CLI 进程始终在该 workspace 中执行。
- CLI 输出分为两层：回答文本进入气泡，执行过程进入气泡下方流程块。
- 执行过程随消息保存，用户后续可追溯 Agent 做了什么。
- “单文件不超过 300 行”不再作为硬规则。文件应按真实职责边界拆分，而不是为了行数强行拆分。
- Codex 中转模式必须使用中转 API Key。ChatGPT 登录 token 不能作为第三方 gateway 凭证。
- AgentHub 应帮助用户修复本机 Codex 配置，而不是要求用户手动编辑 `~/.codex`。
- 2026-06-05 追加修复：旧 `env_key = "CODEX_API_KEY"` 会让本机 Codex 新会话要求进程环境变量，和 AgentHub 写 `.env` 的托管方式冲突。已改为 command-backed auth helper，并已迁移当前本机 `C:\Users\28109\.codex\config.toml`。

## 4. 剩余工作

- Artifact Bridge 核心闭环已在 6F 验收通过；后续从 `docs/deliverables/phase6-artifact-bridge/` 接续。
- 持续从真实 Claude Code、Codex、OpenCode 输出中补充 parser fixture，尤其是命令、文件路径和工具参数细节。
- 为长时间运行的 CLI 进程补充前端显式取消/终止入口。
- 建立可重复的真实 CLI smoke 清单，记录 CLI 版本、认证模式、workspace 文件断言和失败日志。
- Phase 7 继续处理 Artifact Drawer、审批卡片、环境体检和旧 orchestrator 术语残留。

## 5. 交接入口

后续工作优先从这些文件开始：

- `backend/app/agents/cli_adapters.py`
- `backend/app/agents/cli_runtime.py`
- `backend/app/agents/cli_output_parser.py`
- `backend/app/services/single_cli_chat_stream.py`
- `backend/app/services/codex_local_config_service.py`
- `frontend/src/components/ExecutionTracePanel.tsx`
- `frontend/src/components/AgentCliForm.tsx`
- `frontend/src/hooks/useSendMessage.ts`

调试真实 CLI 行为时，先抓取能复现问题的最小 stdout/stderr 样本，再补 parser 或 stream 回归测试，最后改 UI 展示。

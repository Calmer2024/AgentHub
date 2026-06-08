# Spec: Phase 6B-6E — CLI Agent 适配器

**版本**: v3.2
**更新日期**: 2026-06-05
**状态**: Implementation Baseline
**关联 ADR/PRD**: [ADR-0005](../../adr/0005-target-architecture.md)、[ADR-0009](../../adr/0009-project-workspace-model.md)、[ADR-0011](../../adr/0011-agent-engine-skill-model.md)、[PRD-01](../../PRD/01-Architecture_Adapter.md)
**依赖模块**: Phase 6A Workspace Runtime、Phase 3 EventBus / BaseAgentAdapter

---

## 1. 目标

将用户本机安装的真实 CLI 工具（Claude Code、Codex、OpenCode）接入 AgentHub 的运行时。按 [ADR-0011](../../adr/0011-agent-engine-skill-model.md) 的新口径，这些 CLI 工具是 **Engine**，不是用户最终调度的 Agent 本体。用户可见 Agent Profile = System Prompt + Rules + Skills + Context Policy + Runtime Config + Engine；用户在 Project 下与某个 Agent Profile 发起私聊时，后端会为该 Profile 选择的 Engine 在 Project 目录中启动一个 CLI 实例。

本模块通过 PTY/subprocess 管理每个对话对应的 CLI 进程生命周期，实现 stdin/stdout 桥接、ANSI 清洗、交互式拦截，并把 CLI 输出转换为标准化事件（`agent.output` / `artifact.detected` / `interactive_prompt`），最终实现分层渲染——文本进消息气泡、进度进状态条、产物进 Artifact Card、交互进确认卡片。

当前实现快照见 [CLI Adapter 交付文档](../../deliverables/phase6-cli-adapter/README.md)。截至 2026-06-05，真实本机 Claude Code、Codex、OpenCode 三条 CLI Engine 路径已接入后端和前端配置 UI；Codex 支持官方 OpenAI 与第三方中转 API，并由 AgentHub 托管本机 `CODEX_HOME` 下的稳定配置。Agent Profile 的 Skill 绑定与 Prompt Assembly 见 [03-agent-engine-skill-profile.md](03-agent-engine-skill-profile.md)。

**成功标准**（可证伪）：

- [x] 好友列表预置三个 Agent：Claude Code、Codex、OpenCode，各自显示名称、头像、版本号、状态
- [x] 用户点击 Agent 的 ⋮ → [发起对话] → 选择 Project → 在对话列表栏出现新会话 → 自动进入聊天
- [x] 用户发送消息 → ClaudeCodeAdapter / CodexAdapter / OpenCodeAdapter 启动真实本机 CLI 进程（cwd=Project.workspace_path）→ 聊天流出现回复文本 + 执行轨迹块
- [x] 同一 Project 下创建多个 CLI 私聊 → 后端启动独立 CLI 进程（不同 PID），互不影响
- [ ] Claude Code 输出 `Do you want to run this? (y/n)` → 聊天流弹出确认卡片 → 用户点击"同意"→ stdin 写入 `y\n` → 进程继续 → 卡片消失
- [ ] 三个 CLI 的 Adapter 分别能正确识别各自 CLI 的 diff 输出格式并转为 `artifact.detected` 事件
- [x] 不通过标准：任一 CLI Adapter 对 ANSI 码处理不净导致前端出现乱码；任一 CLI 的交互式提示未被拦截导致进程永久挂起

---

## 2. 全局定位

### 2.1 北极星链路位置

```text
用户创建 Project → 在 Project 下配置 Agent Profile（Engine + Skills）
  → 创建私聊/群聊 → 发送消息
  → [本模块] 根据 Agent Profile 的 Engine 路由到对应 Adapter 子类（ClaudeCode/Codex/OpenCode）
  → PTY/subprocess 孵化 CLI 进程（cwd = Project.workspace_path）
  → stdin 注入 prompt → stdout 读取 → ANSI 清洗 → 交互拦截 → 分层解析
  → 标准化事件 → SSE/WebSocket 推送到前端
  → 前端分层渲染（文本→消息、进度→状态条、产物→Card、交互→卡片）
  → Artifact Bridge 创建 Artifact → 消息级 ArtifactCard
```

### 2.2 上下游契约

| 方向 | 模块/事件/API | 本模块的角色 |
|------|-------------|------------|
| **上游输入** | WorkspaceService.get_workspace_path(session_id) → cwd；AgentConfig（executable、init_args、env vars）；用户聊天消息 / Orchestrator 子任务 | 消费 workspace_path 作为进程 cwd；消费 AgentConfig 作为进程启动参数 |
| **下游产出** | `agent.output`（文本块）、`interactive_prompt`（确认请求）、`artifact.detected`（产物信号）、进程生命周期事件（started/completed/timeout） | 产出标准化事件供 SSE 推送和 Artifact Bridge 消费 |
| **本模块不通** | 不创建 Artifact 数据库记录（→ Artifact Bridge）；不渲染消息级 ArtifactCard（→ Phase 6F）；不在 AgentHub 内安装 CLI 工具（用户在外部安装） | |

---

## 3. 跨模块契约

### 3.1 API 端点

| 端点 | 方法 | 请求体 | 成功响应 | 错误响应 |
|------|------|--------|---------|---------|
| `/api/sessions/{id}/chat` | POST | `{ "message": string, "agentId": string }` | SSE 流: `event: agent.output \| interactive_prompt \| agent.process.completed` | `400`、`404` |
| `/api/sessions/{id}/interactive_reply` | POST | `{ "processId": string, "reply": "y" \| "n" }` | `200: { "status": "acknowledged" }` | `404`（进程不存在）、`408`（超时） |

### 3.2 事件

| 事件类型 | 方向 | payload 字段 |
|---------|------|-------------|
| `agent.output` | Adapter → SSE | `{ sessionId, agentId, messageId, chunk: string, chunkType: "text" \| "progress" \| "artifact_signal" }` |
| `interactive_prompt` | Adapter → SSE | `{ sessionId, agentId, processId, content: string, promptType: "confirm" }` |
| `agent.process.started` | Adapter → EventBus | `{ sessionId, agentId, processId, executable, cwd }` |
| `agent.process.completed` | Adapter → EventBus | `{ sessionId, agentId, processId, exitCode }` |
| `agent.process.timeout` | Adapter → EventBus | `{ sessionId, agentId, processId, reason: "silence" \| "heartbeat" \| "total_time" }` |

### 3.3 数据库 Schema 变更

```sql
ALTER TABLE agent_configs ADD COLUMN executable VARCHAR(255);
ALTER TABLE agent_configs ADD COLUMN init_args JSON;
ALTER TABLE agent_configs ADD COLUMN env_vars JSON;
```

### 3.4 跨组件 TypeScript 类型

```typescript
// Engine runtime config 代表用户本机安装的一个 CLI 工具实例。
// Agent Profile 会在这个 Engine 之上绑定 primary/auxiliary skills。
interface AgentCLI {
  id: string;
  name: string;              // 显示名称，默认取 CLI 工具名（"Claude Code" / "Codex" / "OpenCode"）
  agentType: 'cli_wrapper';
  cliTool: 'claude_code' | 'codex' | 'opencode' | 'custom';
  executable: string;        // e.g. "claude", "codex", "opencode"
  initArgs: string[];        // e.g. ["--compact", "--no-color"]
  envVars: Record<string, string>;
  status: 'ready' | 'not_found' | 'error';  // 可执行文件检测状态
  version?: string;          // e.g. "v1.2.3"
  executablePath?: string;   // e.g. "/usr/local/bin/claude"
}

// 好友列表中的每个条目
interface FriendEntry {
  agentId: string;
  displayName: string;       // "Claude Code"
  avatar: string;            // CLI 工具 logo 图标
  status: 'ready' | 'not_found' | 'running' | 'error';
  version?: string;
  activeSessionCount: number; // 当前有多少个活跃对话在使用此 Agent
}

interface InteractivePromptEvent {
  type: 'interactive_prompt';
  sessionId: string;
  agentId: string;
  processId: string;
  content: string;
}
```

---

## 4. 行为规格

### 4.1 正常流程

```
1. 系统 → 预置三个 Agent 在好友列表中（Claude Code / Codex / OpenCode），executable 和 init_args 预设默认值
2. 用户 → 在项目栏选中 Project（如 📁 我的网站）
3. 用户 → 在对话列表栏点击 [+ 新建聊天] → [👤 私聊] → 选择 [🤖 Claude Code]
4. 前端 → POST /api/sessions { projectId, mode: "single", agentId }
5. 用户 → 在输入框输入"写一个登录页面" → 按 Enter
6. 后端 → ChatService → 路由到 ClaudeCodeAdapter
7. ClaudeCodeAdapter → 从 WorkspaceService 获取 cwd → 启动新的 `claude -p --verbose --output-format stream-json --include-partial-messages --dangerously-skip-permissions` 进程（cwd=Project.workspace_path）
8. 进程 stdout → StreamSanitizer 清洗 ANSI → 分层解析（文本/进度/产物/交互）
9. 文本 → SSE agent.output（chunkType="text"）→ 前端消息气泡打字机
10. 进度 → SSE agent.trace.delta / agent.output（chunkType="progress"）→ 前端消息气泡下方执行轨迹面板，运行时展开、完成后自动折叠，并随消息 metadata 持久化
11. HTML 代码块 → SSE 携带 artifact_signal → 前端不展示在消息中，由 Artifact Bridge 异步处理 → Artifact Card 出现
12. 用户看到完整的文本回复 + Artifact Card + 预览按钮
```

### 4.2 Per-CLI 交互模式差异化

三个 CLI 的正常流程在上述步骤 7-11 中因 CLI 不同而在以下维度上有差异：

| 维度 | Claude Code (`claude`) | Codex (`codex`) | OpenCode (`opencode`) |
|------|----------------------|-----------------|----------------------|
| **启动命令** | `claude -p --verbose --output-format stream-json --include-partial-messages --dangerously-skip-permissions` | `codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --color never --json -` | `opencode --no-color --plain` |
| **认证来源** | 用户本机 `claude` 登录态 / 宿主环境 | 用户本机 `codex` 登录态 / 宿主环境 | 用户本机 `opencode` 配置 / 宿主环境 |
| **prompt 注入** | stdin 写入 `{prompt}\n` | stdin 写入 `{system_prompt}\n\n{prompt}\n` | stdin 写入 `{prompt}\n` |
| **文本输出** | Markdown 段落 | Markdown 段落 | Markdown 段落 |
| **进度指示** | `⏺ 正在读取文件...` `⎿ 调用工具: X` | `Working...` + spinner 字符 | `[Tool: Read]` `[Tool: Write]` |
| **diff 输出** | unified diff (`@@ -n,n +n,n @@`) | fenced diff block + git header | 两者混合 |
| **交互特征** | `Do you want to run/proceed? (y/n)` | `Create file X?` `Proceed? [y/N]` | `Apply these changes?` `Continue?` |
| **任务完成** | `✓ 已完成:` | `## Result` | 无固定标记（stdout 结束 = 完成） |

### 4.3 UX 六态覆盖

| 状态 | 用户看到什么 | 触发条件 |
|------|------------|---------|
| **空态-好友列表** | 项目栏顶部 "👥 好友" 区域展示三个预置 Agent（Claude Code / Codex / OpenCode），每个显示头像 + 名称 + 版本 + 绿色 ● 状态点 | 首次使用，已预置 |
| **空态-对话** | 进入新私聊后，对话页面显示 Agent 头像 + 名称 "Claude Code" + 状态指示灯 ⚪ 空闲，下方输入框可输入消息 | 刚创建私聊，未发送消息 |
| **加载态-连接** | 对话页面顶部状态指示灯变为 🟡，输入框上方出现状态条："🔧 正在启动 Claude Code..."+ spinner | 消息已发送，CLI 进程正在启动 |
| **加载态-执行** | 消息气泡逐字出现（打字机效果）；状态条动态更新（如 "⏺ 正在读取文件..."）→ 不进入消息历史 | CLI 正在执行，stdout 正在输出 |
| **正常态** | 消息气泡完整显示 Agent 回复的 Markdown；顶部指示灯恢复 ⚪；如有产物，消息下方出现 Artifact Card | Agent 执行完成，exit_code=0 |
| **错误态** | 见 §4.4 | |
| **边界态** | 用户快速连续发送 3 条消息 → 消息排队（第二条等第一条 CLI 进程结束后才发送）；用户关闭网页 → SSE 断开 → 3 分钟后后端 SIGTERM；消息长度 > 10000 字符 → 自动拆分为多条 SSE chunk；好友列表中同一 Agent 有 3 个活跃对话 → 每个对话独立运行一个 CLI 进程 | |

### 4.4 错误处理

| 错误场景 | 错误码 | 用户可见文案 | 恢复路径 |
|---------|--------|------------|---------|
| executable 不在 PATH 中 | — | "❌ 未找到 '{executable}' 命令。请在终端中安装后重试。" + 安装指引链接（AgentPanel 创建时即校验） | 安装 CLI 后在 AgentPanel 重新检测 |
| Session 未绑定 Project → 无 workspace_path | — | "❌ 当前会话未绑定项目，无法启动 CLI Agent" | 创建 Project 后重试 |
| CLI 未登录或认证失效 | — | "❌ {CLI 名称} 本机认证不可用。请先在终端完成该 CLI 的登录/认证后重试。" | 在系统终端修复 CLI 登录态后重试 |
| CLI 进程静默超时（5 min 无输出） | — | "⏱️ CLI 进程已超时（5 分钟无响应），已自动终止" | 重新发送消息 |
| CLI 进程崩溃（非零 exit） | — | "❌ CLI 进程异常退出（exit code: {n}）" + 最后 500 字符输出 | 检查错误信息，修正后重试 |
| WebSocket 断开超过 3 min | — | 重新连接后显示"⚠️ 之前的会话已断开，进程已终止" | 重新发送消息 |
| 交互式提示超时（等待用户响应 > 2 min） | 408 | "⏱️ 确认已超时，操作已自动取消" | 重新触发 |
| 进程总执行超过 30 min | — | "⏱️ 进程已运行超过 30 分钟，已自动终止" | 缩小任务范围后重试 |

---

## 5. 前端交互序列

### 5.0 核心概念

**Engine ≠ Agent Profile**。本模块负责接入用户本机安装的实际 CLI 工具实例（如 `claude`、`codex`、`opencode`），它们是 Engine。用户真正看到和调度的是 Agent Profile，例如“前端专家 = Claude Code Engine + frontend_engineer Skill”。用户打开一个私聊对话时，后端会为该 Agent Profile 启动对应 Engine 的 CLI 执行单元。执行单元生命周期由 Adapter 能力决定：短进程 Adapter 在本轮对话结束后退出；Claude Code 当前由 `CliSessionProcessRuntime` 维护一会话一常驻 stdin JSONL 进程，并通过 `--session-id` / 崩溃恢复时的 `--resume` 绑定同一个原生会话；Codex/OpenCode 当前由 `CliRpcSessionRuntime` 维护一会话一常驻 RPC 进程。不同 AgentHub 会话之间的 CLI 进程或 Engine session 互不共享状态。

**好友列表**位于项目栏顶部（见 [00-workspace-runtime.md](00-workspace-runtime.md) §5.0 全局布局），展示已配置的 Agent Profile。每个 Agent Profile 显示：用户定义名称 + Engine + Skill 摘要 + 状态。

### 5.1 好友列表与默认 Agent

```
项目栏顶部 "👥 好友" 区域：
  ┌────────────────────┐
  │ 👥 好友        [+] │  ← [+] 按钮：添加新的 CLI Agent
  │                    │
  │  🤖 Claude Code  ⋮ │  ← 预置的 Claude Code Agent
  │     v1.2.3 · 就绪  │     头像 + 名称 + 版本 + 状态
  │                    │     ⋮ 按钮 → 展开操作菜单
  │  🤖 Codex       ⋮ │
  │     v0.9.1 · 就绪  │
  │                    │
  │  🤖 OpenCode    ⋮ │
  │     v2.0.0 · 就绪  │
  └────────────────────┘

系统预置三个默认 Agent（Claude Code / Codex / OpenCode），用户可直接使用。
executable 字段预设默认值，init_args 预设最佳参数。
```

### 5.2 添加新的 CLI Agent（从本机接入）

```
用户: 在好友列表顶部点击 [+]
  → 前端: 弹出 AddAgent 弹窗
    - CLI 工具下拉: [Claude Code] [Codex] [OpenCode] [自定义...]
    - executable 输入框（随选择自动填充，如 "claude"；自定义则手动输入路径）
    - init_args 输入框（自动填充默认值：Claude Code → "-p --verbose --output-format stream-json --include-partial-messages --dangerously-skip-permissions"；Codex → "exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --color never --json -"；OpenCode → "--no-color --plain"）
    - env_vars 折叠区：key-value 编辑器（高级覆盖项；默认留空，继承本机 CLI 登录态）
    - 底部：[检测可执行文件] 按钮 + 状态指示灯
  → 用户: 点击 [检测可执行文件]
  → 前端: GET /api/agents/check-executable?path=claude
  → 后端: 在 PATH 中搜索 → 返回 { found: true, version: "v1.2.3", path: "/usr/local/bin/claude" }
  → 前端: 指示灯变绿 ✓ + 显示版本号 + 路径
  → 用户: 点击 [添加]
  → 前端: POST /api/agents { agentType: "cli_wrapper", executable, initArgs, envVars }
  → 后端: 写入 agent_configs → 返回 201
  → 前端: 弹窗关闭 → 好友列表刷新 → 新 Agent 出现

如果 [检测可执行文件] 返回 { found: false }：
  → 指示灯变红 ✗ + "未找到 {executable}。请先在终端安装：npm install -g @anthropic-ai/claude-code"
  → [添加] 按钮置灰（禁止添加不存在的 CLI）
```

### 5.3 Agent 操作菜单（⋮ 按钮）

```
用户: 在好友列表中点击 Claude Code 右侧的 ⋮ 按钮
  → 前端: 弹出下拉菜单：
    [💬 发起对话]
    [⚙️ 设置]
  → 用户: 点击 [💬 发起对话]
  → 前端: 检测当前是否有选中的 Project：
    - 有选中 Project → 直接在该 Project 下创建私聊 Session → 自动进入聊天
    - 无选中 Project → 弹出 Project 选择器：
        "请先选择一个项目来开始对话"
        列表展示所有 Project（📁 我的网站 / 📁 后台系统） + [+ 新建项目]
  → 用户: 选择一个 Project（或新建）→ 前端: POST /api/sessions { projectId, mode: "single", agentId }
  → 后端: 创建 Session（自动绑定 project_id）→ 返回 201
  → 前端: 对话列表栏刷新 → 自动进入新创建的对话
```

```
用户: 点击 ⋮ → [⚙️ 设置]
  → 前端: 打开 Agent 设置面板（见 §5.4）
```

### 5.4 Agent 设置面板

```
用户: 通过 ⋮ → [⚙️ 设置] 进入某 Agent 的设置面板
  → 前端: 在对话页面区域显示设置表单（覆盖聊天视图）
    - 顶部：Agent 头像 + 名称 + 版本号 + 状态指示灯
    - "可执行文件路径" 输入框（默认值，可修改）
    - "启动参数" 输入框（默认值，可追加）
    - "环境变量" 折叠区：key-value 列表
      - 不接收 API Key；如用户确需覆盖某个非敏感运行变量，可手动新增
      - 可新增自定义变量
    - 底部：[检测可执行文件] [恢复默认] [保存]
  → 用户: 修改 init_args → 追加 "--verbose" → 点击 [保存]
  → 前端: PUT /api/agents/{id} { initArgs: ["--compact", "--no-color", "--verbose"] }
  → 后端: 更新 agent_configs → 返回 200
  → 前端: 显示 "✅ 已保存" → 自动返回聊天视图
```

### 5.5 与 Agent CLI 私聊（一个对话 = 一个 CLI 实例）

```
前提: 用户已选中 Project，好友列表中已有 Claude Code Agent

用户: 在对话列表栏底部点击 [+ 新建聊天] → [👤 私聊]
  → 前端: 弹出 Agent 选择列表（展示好友列表中的 Agent）
  → 用户: 选择 [🤖 Claude Code]
  → 前端: POST /api/sessions { projectId, mode: "single", agentId }
  → 后端: 创建 Session → 返回 201
  → 前端: 对话列表栏出现新对话 "Claude Code · 刚刚" → 自动进入
  → 前端: 对话页面顶部显示 "Claude Code" + 状态指示灯 ⚪ 空闲

用户: 输入 "写一个登录页面" → 按 Enter
  → 前端: 用户消息气泡（右对齐）
  → 前端: POST /api/sessions/{id}/chat → 接收 SSE
  → 前端: Agent 消息气泡出现（左对齐）+ 气泡下方执行轨迹面板显示 "正在启动 Claude Code..."
  → 后端: ClaudeCodeAdapter 启动新的 `claude` 进程（cwd=Project.workspace_path）
         ← 这个进程就是一个独立的 Claude Code 实例
  → SSE: agent.output { chunk: "# 登录页面\n\n", chunkType: "text" }
  → 前端: 气泡打字机追加
  → SSE: agent.output { chunk: "⏺ 正在读取 workspace 文件...", chunkType: "progress" }
  → 前端: 执行轨迹面板追加过程记录
  → SSE: agent.process.completed { exitCode: 0 }
  → 前端: 执行轨迹面板标记完成并自动折叠
  → artifact.created → Artifact Card 出现在消息下方

如果用户在同一 Project 下再创建一个 Claude Code 私聊：
  → 后端启动另一个独立的 `claude` 进程（不同 PID）
  → 两个对话的 Claude Code 实例互不影响
```

### 5.6 交互式确认

```
CLI 进程: stdout 输出 "... Do you want to run this? (y/n) "
  → PromptInterceptor: 检测到匹配 → 暂停 SSE text_chunk 推送
  → SSE: interactive_prompt { content: "Do you want to run this? (y/n)", processId: "pid_123" }
  → 前端: 聊天流中弹出 InteractivePromptCard
    - 卡片内容：⚠️ 图标 + 提示文字 + [✅ 同意(Y)] [❌ 拒绝(N)]
    - 卡片位置：Agent 消息气泡下方
  → 用户: 点击 [✅ 同意(Y)]
  → 前端: POST /api/sessions/{id}/interactive_reply { processId: "pid_123", reply: "y" }
  → 后端: process.stdin.write(b'y\n') → process.stdin.flush()
  → 恢复 stdout 读取 → SSE text_chunk 继续推送
  → 前端: 卡片消失 → 消息气泡继续追加
```

---

## 6. 验收标准

- [ ] AC-01: 好友列表预置三个 Agent（Claude Code / Codex / OpenCode），各自显示名称 + 头像 + 版本 + 状态
- [ ] AC-02: 好友列表 [+] 按钮 → 弹出添加 Agent 弹窗 → 选择 CLI 工具 → executable 自动填充
- [ ] AC-03: 点击 [检测可执行文件] → `which claude` → 返回 found:true + version → 绿色指示灯
- [ ] AC-04: Agent ⋮ 菜单 → [发起对话] → 选择 Project → 对话列表栏出现新会话 → 自动进入聊天
- [ ] AC-05: 无选中 Project 时 [发起对话] → 弹出 Project 选择器 → 选或新建 Project 后创建会话
- [ ] AC-06: 发送消息 → `claude` 进程以 `cwd=project.workspace_path` 启动 → SSE 流式返回
- [ ] AC-07: Claude Code 输出的 Markdown 文本 → agent.output（chunkType="text"）→ 前端打字机（< 100ms）
- [ ] AC-08: Claude Code 输出的 `⏺ 正在读取` → agent.output（chunkType="progress"）→ 前端状态条更新
- [ ] AC-09: HTML fenced code block → artifact_signal → Artifact Bridge → artifact.created → Artifact Card 出现
- [ ] AC-10: Claude Code 输出 `Do you want to run? (y/n)` → 前端弹出 InteractivePromptCard → 同意 → stdin 写入 `y\n`
- [ ] AC-11: 同一 Project 下两个 Claude Code 私聊 → 两个独立的 `claude` 进程 → 互不影响
- [ ] AC-12: 用户关闭网页 → 3 分钟后进程 SIGTERM → 前端显示超时提示
- [ ] AC-13: ANSI 码 `\x1b[31mError\x1b[0m` → 前端收到 `Error`（无乱码）
- [ ] AC-14: 三个 Adapter 各自正确识别对应 CLI 的 diff/交互/进度格式
- [ ] AC-15: Session 未绑定 Project → 发送消息 → 返回明确错误提示

---

## 7. 测试策略

### 7.1 单元测试 (50 条)

| 测试对象 | 条数 | 覆盖内容 |
|---------|------|---------|
| CliProcessManager | 8 | spawn/terminate/超时/环境变量构造/Windows fallback |
| StreamSanitizer | 8 | ANSI 去除/中文/混合/TUI 降级/进度条转换 |
| PromptInterceptor | 6 | 匹配/不匹配/滑动窗口/边界/多模式同时 |
| CliAgentAdapter (基类) | 8 | chat_stream/错误处理/中断/恢复/cwd 校验 |
| ClaudeCodeAdapter | 5 | Claude Code 输出解析/diff 检测/交互匹配/artifact_signal 生成 |
| CodexAdapter | 5 | Codex 输出解析/计划识别/文件创建确认/artifact_signal 生成 |
| OpenCodeAdapter | 5 | OpenCode 输出解析/工具调用日志/审查反馈/artifact_signal 生成 |
| AgentConfig 模型 | 5 | validation/agent_type 枚举/init_args/executable 必填校验 |

### 7.2 集成测试

- 测试 CLI fixture：输出含 ANSI 码文本 → 阻塞提示 → 恢复输出 → 验证 SSE 事件序列
- 三个 Adapter 分别用对应 CLI 的样例输出验证：Claude Code 格式 → 正确分层；Codex 格式 → 正确分层；OpenCode 格式 → 正确分层
- 真实 CLI Smoke test（本机 CLI 已安装且认证可用时）：每个 CLI 一条最短任务，验证真实 workspace 文件写入

### 7.3 E2E 测试

- 前端创建 Claude Code Agent → 发送消息 → 打字机 + 状态条 → Diff → Artifact Card → 交互卡片点击 → 进程继续
- 前端创建 Codex Agent → 同上流程
- 前端创建 OpenCode Agent → 同上流程

---

## 8. 架构约束追溯

| 本模块的决策 | 依据 |
|------------|------|
| CLI Wrapper 是唯一 Agent 执行模式 | PRD-00 §核心变革点 + PRD-01 §2.2 |
| Agent 适配器通过 PTY/subprocess 管理 CLI 进程 | PRD-01 §3.1 |
| cwd = Session → Project.workspace_path | ADR-0009 §核心规则 3 |
| Adapter 不直接写业务表，只输出标准事件 | PRD-01 §3.4 |
| CLI 工具由用户在外部安装，AgentHub 只管理配置 | ADR-0009 §配套决策 A |
| 每个 CLI 单独适配（子类化 CliAgentAdapter） | ADR-0009 §配套决策 B |
| stdout 语义分层解析（文本/进度/产物/交互） | ADR-0009 §配套决策 C + PRD-01 §3.5 |
| ANSI 清洗 + TUI 组件降级 | PRD-01 §3.2 |
| 交互式阻塞匹配 + 滑动窗口 + stdin 回写 | PRD-01 §3.3 |
| 僵尸进程防范（心跳超时 + 静默超时 + 总时间上限） | PRD-01 §4.1 |

---

## 9. 依赖

| 依赖模块 | 需要的接口 | 当前状态 |
|---------|-----------|---------|
| Phase 6A WorkspaceService | `get_workspace_path(session_id) → str`；`GET /api/sessions/{id}/workspace` | ✅ 已验收 |
| Phase 3 EventBus | `publish(event_type, payload)` | ✅ 已就绪 |
| Phase 3 BaseAgentAdapter | 抽象基类 | ✅ 已就绪 |
| Phase 5 ArtifactService | 消费 `artifact.detected` 事件 | ✅ 已就绪 |
| AgentConfig 模型 | `executable` + `init_args` + `env_vars` 字段 | 🔧 需 ALTER TABLE |

---

## 10. Non-Goals（明确不做什么）

| 不做的事 | 原因 | 由谁负责 |
|---------|------|---------|
| 不在 AgentHub 内安装 CLI 工具 | 用户自行在系统层面安装 | 用户 |
| 不写 Artifact 数据库记录 | Adapter 只上报 artifact_signal | Phase 6F Artifact Bridge |
| 不做 CLI 工具的多版本管理 | 超出范围 | 用户 |
| 不做 CLI 工具的输出翻译/多语言 | 保持原始输出 | — |
| 不渲染消息级 ArtifactCard / 审批卡片 | 下游链路 | Phase 6F / Phase 7 |
| 不做远程 CLI 执行（SSH 到远端执行） | P1 本机版范围外 | P2 |

---

## 11. 破坏性变更与迁移

| 维度 | V1 行为 | V2 行为 | 迁移路径 |
|------|--------|--------|---------|
| agent_configs 表 | 无 executable/init_args/env_vars 字段 | 新增三列；agent_type 新增 `cli_wrapper` | ALTER TABLE 自动迁移，已有 Agent 的字段为 NULL |
| AgentPanel | 只显示 API 代理配置 | 新增 CLI 包装器模式 + executable 检测 | 前端新增组件，不影响已有 Agent |
| 纯聊天 Session | 之前可直接无 workspace 单聊 | 所有聊天必须归属 Project | 数据迁移脚本：为旧 Session 创建默认 Project |

> **版本历史**
> - v1.0 (2026-06-02): 初始版本（通用抽象层）
> - v2.0 (2026-06-04): 新增 Per-CLI 接入方案（§8）+ 分层渲染
> - v3.0 (2026-06-04): 按新 Spec 模板全面重构：跨模块契约、六态覆盖、前端交互序列、架构追溯
> - v3.1 (2026-06-04): 同步 Phase 6A 已验收状态；CLI Adapter 可直接消费 Session→Project workspace 查询能力
> - v3.2 (2026-06-05): 同步 CLI Adapter 实现基线、Codex 官方/中转配置托管、执行轨迹块与交付文档

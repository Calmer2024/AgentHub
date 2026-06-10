# SaaS 内置 CLI Engine 配置手册

> 本手册面向 SaaS Web 用户，说明 Claude Code、Codex、OpenCode 三个内置 CLI Engine 的凭据应该在哪里配置、每个字段填什么、什么时候需要改默认值。

---

## 一句话结论

AgentHub SaaS 的三个内置 Engine 是每个用户自己的配置：

| Engine | 主要用途 | 默认 Provider | 默认 Env Key |
|--------|----------|---------------|--------------|
| Claude Code | 代码理解、改造、复杂工程任务 | Anthropic | `ANTHROPIC_API_KEY` |
| Codex | 代码生成、补丁、测试循环 | OpenAI | `AGENTHUB_CODEX_API_KEY` |
| OpenCode | OpenCode CLI 与兼容 Provider | OpenAI 兼容 | `AGENTHUB_OPENCODE_API_KEY` |

配置入口在“智能体”里，不在工作区设置里。一个用户配置一次后，该用户的项目、工作区、内置 Engine 和自定义 Agent 都可以复用这套 Engine 凭据。

---

## 配置入口

1. 登录 AgentHub SaaS Web。
2. 打开左侧“智能体”或好友列表。
3. 选择内置 Engine：Claude Code、Codex 或 OpenCode。
4. 打开“智能体设置”。
5. 在“Engine 凭据”区域填写 Provider、Base URL、模型、Env Key 和 API Key。
6. 点击“保存”。

保存后，API Key 会进入云端 Secret。后续再次编辑时，API Key 输入框显示“已保存，留空则沿用”；如果不想换 Key，可以留空保存其他字段。

---

## 不要把 CLI Key 配到哪里

| 位置 | 用途 | 是否放 CLI API Key |
|------|------|--------------------|
| 智能体 → Engine 凭据 | 配置 Claude Code、Codex、OpenCode 运行凭据 | 是 |
| 工作区设置 | 查看项目、云端 workspace、快照、导入等信息 | 否 |
| Project Secret | 给项目代码运行时使用的环境变量，例如应用自己的数据库密码、第三方服务 Key | 通常否 |
| System Prompt / Rules | 定义 Agent 身份、规则、工作方式 | 否 |

团队项目中也使用你自己的 Engine 凭据来运行你发起的 Agent。不要把个人 API Key 发给队友，也不要写进聊天消息、Prompt、代码文件或项目 Secret。

---

## 通用字段说明

### Provider

选择这个 Engine 连接哪类服务：

| 选项 | 什么时候选 |
|------|------------|
| 官方 API | 使用 Anthropic、OpenAI 等官方 API Key 直连 |
| 中转 API | 使用兼容官方协议的中转站、代理站、企业网关 |
| CC Switch | 使用 CC Switch 或 Claude Code 兼容路由，把 Claude Code 请求切到其他模型或中转服务 |
| 自定义 | Provider 不属于以上三类，且你明确知道它要求的 Base URL、模型名和鉴权环境变量 |

### 模型

填写 Provider 要使用的模型名。模型名必须以 Provider 当前文档为准。

可以先留空，让 CLI 或 Provider 使用默认模型；当中转站要求指定模型、或你需要固定模型时再填写。

### Provider ID

Provider 的内部标识。它不是密钥，只用于生成云端 CLI 运行配置。

建议使用小写英文、数字、下划线或短横线，例如：

| 场景 | 示例 |
|------|------|
| Anthropic 官方 | `anthropic` |
| OpenAI 官方 | `openai` |
| 公司中转 | `company_proxy` |
| CC Switch | `cc_switch` |

Provider ID 需要稳定且只包含常见英文字符。对 Codex 和 OpenCode，它会成为生成配置里的 provider key；对 Claude Code，它主要用于记录配置来源。它不负责鉴权，填错通常不会直接导致 401，真正决定能不能跑的是 Base URL、模型、Env Key 和 API Key。

### Provider 名称

给用户看的 Provider 名称，例如 `Anthropic`、`OpenAI`、`Company Proxy`、`CC Switch`。

Provider 名称主要用于显示和写入 CLI 配置，可读即可。它不需要和供应商后台完全同名。

### Base URL

API 服务地址，不是官网地址、控制台地址或文档地址。

| 场景 | 填法 |
|------|------|
| Claude Code 使用 Anthropic 官方 | 通常留空 |
| Codex 使用 OpenAI 官方 | `https://api.openai.com/v1` |
| OpenCode 使用 OpenAI 兼容服务 | 按服务商文档填写，通常以 `/v1` 结尾 |
| 中转 API / CC Switch | 填中转站提供的 API endpoint |

如果保存后出现 404、返回 HTML、或 CLI 提示无法解析响应，通常是 Base URL 填成了控制台页面或网页地址。

### Env Key

云端 Runtime 注入 API Key 时使用的环境变量名。默认值已经按三个 Engine 隔离：

| Engine | 默认 Env Key |
|--------|--------------|
| Claude Code | `ANTHROPIC_API_KEY` |
| Codex | `AGENTHUB_CODEX_API_KEY` |
| OpenCode | `AGENTHUB_OPENCODE_API_KEY` |

一般不要改。只有 Provider、企业网关或 CC Switch 文档明确要求使用某个环境变量名时才修改。

### API Key

填写官方服务、中转站或 CC Switch 发给你的密钥。AgentHub 保存后不会在前端回显明文。

首次配置必须填写。以后只改 Provider、Base URL 或模型时，可以留空沿用已保存的 Key。需要轮换密钥时，直接填入新 Key 并保存。

---

## Claude Code 配置

Claude Code 适合复杂代码库理解、跨文件修改、重构、调试和工程任务。SaaS 云端运行时会把你的配置注入 Claude Code 进程。

### 使用 Anthropic 官方 API

| 字段 | 推荐填写 |
|------|----------|
| Provider | 官方 API |
| 模型 | 可留空，或填写 Anthropic 当前文档中的模型名 |
| Provider ID | `anthropic` |
| Provider 名称 | `Anthropic` |
| Base URL | 留空 |
| Env Key | `ANTHROPIC_API_KEY` |
| API Key | 你的 Anthropic API Key |

### 使用中转 API

| 字段 | 推荐填写 |
|------|----------|
| Provider | 中转 API |
| 模型 | 按中转站文档填写；不要求时可留空 |
| Provider ID | 例如 `anthropic_proxy` |
| Provider 名称 | 例如 `Anthropic Proxy` |
| Base URL | 中转站提供的 Anthropic 兼容 API endpoint |
| Env Key | 通常仍用 `ANTHROPIC_API_KEY`，除非中转站另有要求 |
| API Key | 中转站提供的 Key |

### 使用 CC Switch

| 字段 | 推荐填写 |
|------|----------|
| Provider | CC Switch |
| 模型 | CC Switch 路由里配置的模型名；不要求时可留空 |
| Provider ID | `cc_switch` |
| Provider 名称 | `CC Switch` |
| Base URL | CC Switch 提供的 Claude Code / Anthropic 兼容 endpoint |
| Env Key | 按 CC Switch 文档填写；不确定时先用 `ANTHROPIC_API_KEY` |
| API Key | CC Switch 或其上游中转服务的 Key |

### 使用 DeepSeek Anthropic 兼容入口

如果直接使用 DeepSeek 的 Anthropic 兼容 API，可以按下面填写：

| 字段 | 推荐填写 |
|------|----------|
| Provider | 中转 API；如果你确实通过 CC Switch 路由，则选 CC Switch |
| 模型 | `deepseek-v4-pro`，不要包含 `[1m]`、`[0m]` 这类终端颜色残留 |
| Provider ID | `deepseek` |
| Provider 名称 | `DeepSeek` |
| Base URL | `https://api.deepseek.com/anthropic` |
| Env Key | `ANTHROPIC_AUTH_TOKEN` |
| API Key | DeepSeek 控制台生成的 `sk-...` 密钥，不是 Base URL |

---

## Codex 配置

Codex 适合代码生成、补丁、测试循环和较直接的工程执行。AgentHub 会在云端 workspace 里为 Codex 生成独立运行配置，并把密钥注入 `AGENTHUB_CODEX_API_KEY`。

### 使用 OpenAI 官方 API

| 字段 | 推荐填写 |
|------|----------|
| Provider | 官方 API |
| 模型 | 可留空，或填写 OpenAI 当前文档中的模型名 |
| Provider ID | `openai` |
| Provider 名称 | `OpenAI` |
| Base URL | `https://api.openai.com/v1` |
| Env Key | `AGENTHUB_CODEX_API_KEY` |
| API Key | 你的 OpenAI API Key |

### 使用 OpenAI 兼容中转 API

| 字段 | 推荐填写 |
|------|----------|
| Provider | 中转 API |
| 模型 | 中转站要求的模型名；不要求时可留空 |
| Provider ID | 例如 `agenthub_proxy`、`company_proxy` |
| Provider 名称 | 例如 `AgentHub Proxy`、`Company Proxy` |
| Base URL | 中转站提供的 OpenAI 兼容 endpoint，通常以 `/v1` 结尾 |
| Env Key | `AGENTHUB_CODEX_API_KEY` |
| API Key | 中转站提供的 Key |

新版 Codex CLI 已不再接受 `wire_api = "chat"`。AgentHub 云端会生成 `wire_api = "responses"`，因此 Codex 中转站必须支持 OpenAI Responses API；只支持 Chat Completions 的中转站无法保证兼容 Codex。

### 使用 CC Switch 或自定义网关

如果网关暴露 OpenAI 兼容接口，可以选“中转 API”；如果它需要特殊 Provider 标识或环境变量，可以选“CC Switch”或“自定义”。

| 字段 | 推荐填写 |
|------|----------|
| Provider | CC Switch 或自定义 |
| 模型 | 网关路由名或模型名 |
| Provider ID | 网关文档建议的 ID；没有要求时自定义一个稳定 ID |
| Provider 名称 | 给自己识别的名称 |
| Base URL | 网关 API endpoint |
| Env Key | 默认 `AGENTHUB_CODEX_API_KEY`，除非网关要求别的变量 |
| API Key | 网关或中转站提供的 Key |

---

## OpenCode 配置

OpenCode 适合使用 OpenCode CLI 以及各种 OpenAI 兼容或自定义 Provider。AgentHub 会在云端 workspace 里为 OpenCode 生成运行配置，并把密钥注入 `AGENTHUB_OPENCODE_API_KEY`。

### 使用 OpenAI 官方或 OpenAI 兼容服务

| 字段 | 推荐填写 |
|------|----------|
| Provider | 官方 API 或中转 API |
| 模型 | Provider 支持的模型名；可先留空 |
| Provider ID | `openai` 或自定义 Provider ID |
| Provider 名称 | `OpenAI` 或服务商名称 |
| Base URL | 官方默认 `https://api.openai.com/v1`；中转按服务商文档填写 |
| Env Key | `AGENTHUB_OPENCODE_API_KEY` |
| API Key | 官方或中转站提供的 Key |

### 使用自定义 Provider

| 字段 | 推荐填写 |
|------|----------|
| Provider | 自定义 |
| 模型 | Provider 文档中的模型名 |
| Provider ID | Provider 唯一标识，例如 `my_provider` |
| Provider 名称 | Provider 显示名 |
| Base URL | Provider API endpoint |
| Env Key | 默认 `AGENTHUB_OPENCODE_API_KEY`，除非 Provider 文档要求别的变量 |
| API Key | Provider 提供的 Key |

如果不确定 OpenCode Provider 是否兼容，先按“中转 API + OpenAI 兼容 Base URL + 默认 Env Key”配置，再运行一个简单对话验证。

---

## 新用户推荐配置顺序

1. 只有 OpenAI Key：先配置 Codex。
2. 有 Anthropic Key 或 Claude Code 中转：配置 Claude Code。
3. 使用 OpenCode 生态或自定义 Provider：配置 OpenCode。
4. 使用中转站：先看中转站文档确认 Base URL、模型名、协议兼容类型，再选择“中转 API”。
5. 使用 CC Switch：先确认它暴露的是 Claude Code / Anthropic 兼容接口，还是 OpenAI 兼容接口，再选择对应 Engine。

不确定模型名时先留空；不确定 Env Key 时使用 AgentHub 默认值。

---

## 常见错误与处理

| 前端或运行日志提示 | 常见原因 | 处理方式 |
|--------------------|----------|----------|
| 请先配置 Claude Code API Key | Claude Code 从未保存过 Key，或保存时 Key 留空 | 回到 Claude Code 的 Engine 凭据，填写 API Key 后保存 |
| 请先配置 Codex API Key | Codex 从未保存过 Key，或 Secret 不存在 | 回到 Codex 的 Engine 凭据，填写 API Key 后保存 |
| 请先配置 OpenCode API Key | OpenCode 从未保存过 Key，或 Secret 不存在 | 回到 OpenCode 的 Engine 凭据，填写 API Key 后保存 |
| 401 / 403 / unauthorized | Key 无效、额度不足、账号无模型权限、中转站鉴权失败 | 到 Provider 后台检查 Key、余额、权限和模型授权 |
| 404 / HTML response / parse error | Base URL 填成了网页、控制台、文档页，或少了 API 路径 | 改成 Provider 文档里的 API endpoint |
| model not found | 模型名不被 Provider 支持，或中转站映射名不同 | 按 Provider 或中转站文档修改“模型”字段 |
| 自定义 Agent 无法运行 | 这个自定义 Agent 选择的底层 Engine 还没配置 | 先配置对应 Engine 的 API Key |
| 保存后仍提示未配置 | 首次保存时 API Key 为空，或 Env Key 被改成了不存在的 Secret 名 | 重新填写 API Key；Env Key 恢复默认值后再保存 |
| API Key 不能填写 URL | 把 Base URL 粘到了 API Key 输入框 | Base URL 填请求地址，API Key 填供应商控制台生成的密钥 |

---

## 安全建议

- 不要在聊天、Prompt、Rules、代码文件、README 或 Project Secret 里粘贴 CLI API Key。
- 配置页不会回显已保存的 API Key；看到“已保存，留空则沿用”表示 Secret 仍存在。
- 怀疑 Key 泄露时，先到 Provider 后台撤销旧 Key，再回到 AgentHub 填入新 Key 保存。
- 团队协作时，每个成员应使用自己的用户级 Engine 凭据。
- 中转站 Key 与官方 Key 一样敏感；不要因为它不是官方 Key 就降低保护级别。

---

## 本地桌面版说明

本手册只覆盖 SaaS Web 的云端 Engine 凭据。桌面版使用用户本机 CLI 和本机环境变量，配置方式不同，见 [Phase 6 CLI Adapter 使用指南](../deliverables/phase6-cli-adapter/usage-guide.md)。

# 需求规格说明书 (PRD)：AgentHub 总览与北极星指标 (Master Hub)

## 1. 文档元信息
*   **产品名称**：AgentHub (多 Agent 协作平台)
*   **文档编号**：PRD-00-MASTER
*   **文档阶段**：Phase 3 (核心架构重构与交互落地)
*   **目标读者**：业务主管、架构师、全栈开发工程师、产品/UI 设计师
*   **核心关联文档**：
    *   [01-Architecture_Adapter.md](./01-Architecture_Adapter.md) (CLI 适配器设计)
    *   [02-Orchestrator_Engine.md](./02-Orchestrator_Engine.md) (Orchestrator 调度引擎)
    *   [03-User_Experience.md](./03-User_Experience.md) (UI 原型与体验设计)
    *   [04-Data_API_Contracts.md](./04-Data_API_Contracts.md) (数据架构与接口)
    *   [05-End_to_End_Product_Flow.md](./05-End_to_End_Product_Flow.md) (端到端产品闭环与需求追踪)
    *   [06-MVP_Local_Workspace_Delivery.md](./06-MVP_Local_Workspace_Delivery.md) (MVP 本机 Workspace 落地链路)
    *   [07-SaaS_Cloud_Workspace_Delivery.md](./07-SaaS_Cloud_Workspace_Delivery.md) (SaaS 云端 Workspace 落地链路)

---

## 2. 执行摘要 (Executive Summary)
随着大语言模型 (LLM) 能力的爆炸式增长，基于单一会话的对话工具（如 ChatGPT、Claude Web版）已经无法满足现代企业级软件工程和复杂长链路任务的需求。大模型在单次生成长度（Max Output Tokens）、复杂意图的维持（Context Window Degradation）以及自我纠错和调试能力上存在无法逾越的物理瓶颈。

**AgentHub** 的诞生，旨在构建一个**“意图驱动的 AI 协作工作空间”**。它在产品形态上结合了现代 IM 通讯工具（如 Slack/微信）和集成开发环境（IDE）的最佳实践。

**核心变革点**：
本期 PRD 对初期的项目技术方案进行了重大修正。AgentHub 不再是一个简单的“调用大模型 API 并手动拼接 Prompt 的聊天室”。相反，它将作为一层强大的**调度壳 (Orchestration Shell)**，底层直接对接并封装市面上真正具备独立执行能力的 CLI Agent 工具（如 Anthropic 官方的 Claude Code 命令行工具，或开源的 OpenCode 等）。通过提供统一的 UI/UX 层和多进程管理层，彻底释放“自主 Agent”在真实文件系统上编写、调试代码的潜力。

**闭环补充**：
本 PRD 以启动文档为源头，必须覆盖 IM 聊天、多 Agent 协作、Orchestrator、Artifact 预览编辑、AI 协作交付物等课题要求。端到端完成定义见 [05-End_to_End_Product_Flow.md](./05-End_to_End_Product_Flow.md)：用户输入任务后，系统必须能经过 Project 创建/绑定 workspace、Orchestrator/Agent 执行、消息级 Artifact Card、页面级预览/编辑、局部编辑、版本化和审批继续。MVP 默认采用 [06-MVP_Local_Workspace_Delivery.md](./06-MVP_Local_Workspace_Delivery.md) 定义的本机 workspace；SaaS 版采用 [07-SaaS_Cloud_Workspace_Delivery.md](./07-SaaS_Cloud_Workspace_Delivery.md) 定义的云端 workspace。

---

## 3. 问题背景深度剖析 (Problem Statement)

当前企业用户和极客开发者在使用 AI 辅助编程或调研时，面临三大难以克服的痛点，这也构成了 AgentHub 必须解决的核心业务问题。

### 3.1 痛点一：单点模型的“全栈无能”与上下文污染
在传统的聊天界面中，用户常常希望一个模型能够包揽从需求分析、数据库设计到前端开发的全部工作。然而：
*   **角色混乱**：单一模型在长文本中容易发生“角色漂移（Persona Drift）”，前端写着写着就把后端的逻辑混淆进去。
*   **Context 污染**：大量的历史聊天记录、无效的报错信息和重试指令会堆积在同一个对话中，导致模型对关键意图的注意力严重下降，最终陷入“改 A 坏 B，越改越错”的死循环。

### 3.2 痛点二：复杂工程的“万行代码瀑布”与缺乏中间人工审查
真实世界的软件工程绝不是一蹴而就的。
*   如果用户输入：“开发一个完整的图书馆管理系统”。
*   在传统的单次响应系统中，模型会尝试在一次对话中吐出成百上千行的 Markdown 代码。这不仅受限于 4096 Tokens 的物理上限，更可怕的是，如果前置的架构设计（如表结构）是错的，后续生成的所有前端页面都是废纸。
*   传统工具缺乏一种“化整为零”的拆解机制，也缺乏在关键节点（如架构设计完成时）自动暂停并向人类汇报求证（Human-in-the-loop）的机制。

### 3.3 痛点三：产物呈现的割裂与终端恐惧症
真实的 Agent 工具（如 Claude Code）通常运行在黑色枯燥的命令行终端 (CLI) 中。
*   **视觉黑盒**：用户无法直观地看到文件树的变化。
*   **体验割裂**：当命令行 Agent 生成了一个 React 网页时，用户必须自己去命令行启动 `npm run dev`，然后切换到浏览器去看效果，发现不对，再切回命令行打字。这种上下文的频繁切换极大地消耗了脑力。
*   **纯文本局限**：在微信或普通 AI 对话框里，代码只能以文本块存在，无法作为一种被托管的“富媒体资产（Rich Artifacts）”进行历史版本回溯和所见即所得的阅览。

---

## 4. 产品愿景与核心价值主张 (Product Vision & Value Proposition)

AgentHub 的愿景是成为**人类工程师管理 AI 团队的第一工作台**。

### 4.1 核心价值一：化繁为简的三栏动态工作区 (Dynamic Workspace)
AgentHub 摒弃了传统的死板界面。无产物时，它是一个极其克制、沉浸式的聊天工具（左侧导航 + 会话列表 + 聊天框）；当底层 Agent 完成实质性工作（如生成网页、修改大批量代码）时，聊天消息下方会出现**消息级 Artifact Card**。用户通过页面级预览/编辑弹窗查看结果、编辑代码和管理版本，真正实现所见即所得。

### 4.2 核心价值二：降维打击的 CLI Agent 封装 (CLI-as-a-Service)
AgentHub 承认并尊重专业工具的价值。平台不再自己手搓劣质的代码生成循环，而是将 Claude Code 等终端“接入”网页中。
平台在后端通过 `PTY` 和 `Subprocess` 技术接管这些工具的标准输入输出（stdin/stdout）。对上层用户而言，他们只需要在精美的网页聊天框里发号施令；在底层，是货真价实的自动化脚本在宿主机或容器内疯狂读写文件、运行测试。

### 4.3 核心价值三：包工头级别的智能调度引擎 (The Orchestrator)
这是整个 AgentHub 最厚的护城河。
Orchestrator（协调器）本身是一个由顶级大模型驱动的纯决策引擎。它不干脏活，只做统筹。它能将“写个淘宝”这种模糊的宏大叙事，自动拆解为包含严密前置依赖关系的 DAG（有向无环图）任务列表（Task Breakdown）。
它能根据任务图谱，有条不紊地拉起对应的底层 CLI Agent 去执行子任务。在关键时刻，它能挂起流水线，等待用户的“御笔亲批”。

---

## 5. 目标用户画像与使用场景 (Target Personas)

### 5.1 Persona 1: “架构师”极客 (Senior Developer / Tech Lead)
*   **背景**：懂代码，懂大模型的边界，但极其厌恶在不同终端和编辑器之间来回切换。
*   **诉求**：希望有一个统一的地方管理多个领域的 Agent（前端、后端、测试）。在做大项目时，希望大模型能自己把繁杂的体力活干完。
*   **核心场景**：他在 AgentHub 中新建了一个针对他新想法的“群聊”。他在群里 `@Orchestrator` 发布了架构需求。随后，他看着右侧的 DAG 进度图一点点亮起，看着后台的几个 CLI Agent 轮番修改代码，最终在右侧抽屉直接预览整个系统。

### 5.2 Persona 2: “非技术”产品经理/创业者 (Product Manager / Founder)
*   **背景**：不懂配置复杂的编程环境，不懂什么是终端命令行。有强烈的业务点子。
*   **诉求**：极简的交互。我只想要个网页，你别给我看黑框白字的代码。
*   **核心场景**：打开平台，看到中央巨大的“我想做个产品”的输入框。敲下一段话。后台虽然跑的是硬核的 Claude Code，但在前台，他看到的只是一张精美的“资产卡片（Asset Card）”。点击卡片，右侧直接渲染出一个可以点击互动的 H5 页面。

### 5.3 Persona 3: 系统管理员/平台运营者 (Platform Admin)
*   **背景**：负责整个研发团队的工具基建。
*   **诉求**：配置底层大模型 API，接入新的开源 Agent 工具链。
*   **核心场景**：在“Agent 库”面板，他新建了一个名为“安全审查员”的 Agent，底层关联到 `opencode` 可执行文件，并注入了一段强制性的安全审查 System Prompt，随后发布给全公司使用。

---

## 6. 成功衡量指标 (Success Metrics)

为了验证本期核心重构与功能迭代是否成功，制定以下北极星指标与健康度指标：

1.  **复杂任务闭环率 (Complex Task Completion Rate)**：
    定义：包含 3 个及以上拆解子任务的会话，最终能完整跑通并产出最终 Artifact 的比例。预期目标：> 75%。
2.  **人工干预频率 (Human Intervention Rate per Task)**：
    定义：在一个连贯的长任务流中，用户主动修改任务编排或紧急打断运行的次数。这衡量了 Orchestrator 拆解任务的合理性。
3.  **产物卡片打开率 (Artifact Card Open Rate)**：
    定义：生成了 Artifact 资产卡片后，用户点击打开页面级预览/编辑弹窗的比例。预期目标：> 90%，证明产物内联渲染是绝对的刚需。
4.  **CLI 进程异常崩溃率 (CLI Process Crash Rate)**：
    定义：后端 `subprocess` 因处理特殊字符、内存溢出或死锁导致的非正常退出比例。预期目标：< 2%。
5.  **端到端 Artifact 闭环率 (Artifact Loop Completion Rate)**：
    定义：用户从自然语言任务触发 Agent 输出，系统自动生成 Artifact Card，用户完成预览、编辑、确认新版本的比例。预期目标：MVP 演示路径必须 100% 跑通。
6.  **文档覆盖完整度 (Documentation Traceability)**：
    定义：启动文档中的 P0/P1 要求均能追溯到 PRD 与 Spec，Phase 文档均说明全局定位、上下游契约与未覆盖边界。预期目标：P0/P1 无孤儿需求。

---

## 7. 边界与非目标 (Scope & Non-Goals)

在有限的研发资源下，明确什么**不做**比做什么更重要。

1.  **不做重度 Web IDE**：
    页面级 Artifact 预览/编辑弹窗在展示代码时，主要承担预览、Diff、版本管理和受控编辑。**坚决不实现**类似 VS Code 的强交互式编辑（如局部拖拽生成、右键重构等）。代码的增删改查主入口，永远是通过聊天框用自然语言驱动 Agent 去改。
2.  **P1 不做云端沙箱，P2 再做**：
    P1（桌面版）阶段，CLI Agent 进程直接针对本地磁盘的指定 Workspace 进行读写操作，默认信任宿主机环境。P2（SaaS 云版）阶段引入云端容器沙箱隔离，实现多租户安全与一键部署到云端 URL。
3.  **不做去中心化的多 Agent 互聊 (Swarm)**：
    目前所有的任务调度采用绝对的“主从模式”。Orchestrator 处于权力顶峰，向底层 Agent 派发任务，接收结果。底层的打工人 Agent 之间不进行直接的 P2P 聊天对话。
4.  **不做跨会话的向量 RAG**：
    尽管历史资产重用很重要，但本期仅利用 SQLite FTS5 提供基于文本的 `Ctrl+K` 搜索和简单的“引用（Reply）”上下文强注入。不引入复杂的向量嵌入数据库（Vector DB）。

---

## 8. 文档矩阵导航 (Document Hub Navigation)

为了确保各职能线（产品、设计、前端、后端、架构）能够高效找到落地细节，本 PRD 采用分而治之的多文件架构。
请根据您的角色，点击进入对应的子文档以获取详尽的执行标准：

*   👉 **[01-Architecture_Adapter.md](./01-Architecture_Adapter.md)**
    *   **受众**：架构师、后端开发
    *   **摘要**：彻底弄懂我们是如何利用 `subprocess` 和 `PTY` 技术将一个只活在黑框框里的命令行程序（如 Claude Code），封装成 HTTP/WebSocket 接口的。
*   👉 **[02-Orchestrator_Engine.md](./02-Orchestrator_Engine.md)**
    *   **受众**：后端开发、业务中台开发
    *   **摘要**：揭秘平台的大脑。详细讲解 DAG 任务拆解表如何设计，以及任务流水线如何在特定节点自动“挂起”等待老板审批。
*   👉 **[03-User_Experience.md](./03-User_Experience.md)**
    *   **受众**：UI/UX 设计师、前端开发
    *   **摘要**：像素级的界面布局描述。专门用于喂给画图 AI，清晰定义了“环境体检卡”、“中央巨型输入框”、“资产卡片”和“动态三栏抽屉”的形态。
*   👉 **[04-Data_API_Contracts.md](./04-Data_API_Contracts.md)**
    *   **受众**：全栈开发
    *   **摘要**：直接指导代码编写。涵盖了最终的 `agents`, `tasks` 数据库字段设计，以及前后端通信的关键 REST 接口清单。
*   👉 **[05-End_to_End_Product_Flow.md](./05-End_to_End_Product_Flow.md)**
    *   **受众**：产品负责人、架构师、全栈开发、答辩准备人员
    *   **摘要**：对照启动文档建立需求追踪矩阵，定义从 Project 创建/绑定 workspace、IM 输入到 Agent 执行、Artifact 生成、抽屉预览、局部编辑、审批继续的端到端闭环。
*   👉 **[06-MVP_Local_Workspace_Delivery.md](./06-MVP_Local_Workspace_Delivery.md)**
    *   **受众**：产品负责人、后端开发、前端开发、答辩准备人员
    *   **摘要**：定义 MVP 本机 workspace 版的完整落地链路：本机后端创建 Project 并绑定 workspace，CLI Agent 以 `Project.workspace_path` 为 `cwd` 执行，文件变更进入 Artifact，并支持本机预览、导出和可选部署。
*   👉 **[07-SaaS_Cloud_Workspace_Delivery.md](./07-SaaS_Cloud_Workspace_Delivery.md)**
    *   **受众**：产品负责人、架构师、平台工程、商业化规划人员
    *   **摘要**：定义 SaaS 云端 workspace 版的最终形态：云端隔离 workspace、sandbox runner、云端 preview URL、多租户安全和一键部署。

---

## 9. 产品交付阶段 (Product Delivery Phases)

AgentHub 分两个阶段交付，先完成桌面版（P1），再做 SaaS 云版（P2）。

### P1 — 桌面版（当前阶段）

| 维度 | 定义 |
|------|------|
| **产品形态** | 桌面端（Tauri/Node.js 进程）= 本地无头服务器 + 本地特权执行引擎；Web 端（浏览器）= 全功能交互工作区（主力 UI） |
| **数据流** | 用户浏览器 → localhost 后端 → 本机文件系统 + 本机 CLI Agent 进程 |
| **Workspace 位置** | 用户本机文件系统（默认在 `AGENTHUB_WORKSPACE_ROOT` 下，也可绑定用户通过系统目录选择器授权的已有目录） |
| **CLI Agent 运行位置** | 用户主机（直接 spawn subprocess） |
| **部署能力** | ❌ 不支持一键部署（本地运行，无远程服务器） |
| **安全边界** | 基于 allowlist 的本机路径校验；Web UI 通过 localhost 访问后端 |

### P2 — SaaS 云版（远期）

| 维度 | 定义 |
|------|------|
| **产品形态** | Web 端浏览器 + 云端后端 + 云端沙箱 |
| **数据流** | 用户浏览器 → 云端后端 → 云端沙箱 + 云端 CLI Agent 进程 → 一键部署 |
| **Workspace 位置** | 云端隔离沙箱 volume |
| **CLI Agent 运行位置** | 云端容器内 |
| **部署能力** | ✅ 一键部署到云端 URL |
| **安全边界** | 多租户容器隔离、网络策略、配额管理 |

> **版本历史记录**
> * v1.0.0 - 初始版本，基于单调 LLM API 的粗糙设想。
> * v2.0.0 - 历经极限拷问，全面转向真实 CLI 挂载 + Orchestrator DAG 状态机的工业级架构。
> * v2.1.0 - 补齐启动文档需求追踪与端到端 Artifact 产品闭环。
> * v2.2.0 - 补齐 MVP 本机 workspace 与 SaaS 云端 workspace 的落地链路。
> * v3.0.0 (当前) - 全面删除 HTTP API 伪 Agent 历史遗留，确立 CLI Wrapper 为唯一 Agent 架构。明确 P1 桌面版（本机执行）+ P2 SaaS 云版（云端沙箱+一键部署）的分阶段交付策略。
> * v3.1.0 - 2026-06-04：同步 Phase 6A Project-first workspace runtime 验收结果；Project 创建支持新建空白文件夹/系统目录选择器，不再暴露项目类型选择。

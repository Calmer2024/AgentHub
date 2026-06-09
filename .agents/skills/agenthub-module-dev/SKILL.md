---
name: agenthub-module-dev
description: AgentHub 项目标准模块开发流程。当用户要求开发新模块、新功能、新增量时触发。自动执行：读取对应 Spec → 确认接口契约 → 写实现 → 写单元测试 → 验证验收标准。
---

# AgentHub 标准模块开发流程

你正在 AgentHub 项目中进行模块开发。必须严格遵循以下流程，不可跳过任何步骤。

## 开发流程

### Step 0: 创建开发分支
1. 确认当前在 `phase/main` 集成分支上，拉取最新代码：
   ```
   git checkout phase/main && git pull origin phase/main
   ```
2. 从 `phase/main` 创建 Phase 开发分支（命名使用 `phase/` 前缀，而非 `feat/`）：
   ```
   git checkout -b phase/<phase-name> phase/main
   ```
   示例：`phase/phase4-artifact-editing`、`phase/phase3-smart-collab`
3. 小粒度功能可在 Phase 开发分支上再切 `feat/` 或 `fix/` 分支
4. 分支命名遵循 `docs/GIT_PROTOCOL.md` 第 2 节规范
5. **禁止直接在 `phase/main` 上开发**——所有开发必须在 `phase/<name>` 分支上进行，开发完成后合并回 `phase/main`

### Step 1: 读取 Spec
1. 在 `docs/specs/` 目录下找到对应模块的 Spec 文档
2. 如果没有 Spec，**拒绝开始开发**，要求用户先完成 Spec
3. 完整阅读 Spec，确认理解目标、输入输出、行为规格、验收标准
4. 如果模块涉及前端 UI，同时读取 `docs/testing/UX_TEST_SPEC.md`，确认 UX 6 状态覆盖要求

### Step 2: 确认接口契约
1. 检查 Spec 中定义的接口是否与 ADR-0005 中的契约一致
2. 如果本模块对外暴露新接口，先写接口定义（抽象类/类型），再写实现
3. 确认依赖的模块是否已就绪（Spec 第 5 节）
4. 前后端类型同步检查：TypeScript interface ↔ Pydantic schema

### Step 3: 写实现
1. 按照 Spec 的"不在范围内"清单，不写任何超出范围的功能
2. 后端：先写 Pydantic schema → 再写 Service → 最后写 API 路由
3. 前端：先写类型定义 → 再写 Store → 最后写组件
4. 前端每个新组件必须覆盖 UX_TEST_SPEC.md 要求的 6 种状态（空/加载/正常/完成/错误/边界）
5. 遵守 AGENTS.md 中的所有代码规则（避免臃肿文件、禁止 any、async 等）

### Step 4: 写单元测试
1. 按照 `docs/TEST_PROTOCOL.md` 规范编写测试
2. 后端：pytest + httpx AsyncClient + 真实迁移后的文件数据库，覆盖正常流程 + Spec 3.2 每个异常场景
3. 前端：Vitest + testing-library/react，覆盖组件渲染 + Store 逻辑
4. 测试用例直接对应 Spec 第 3 节的每个场景
5. Mock 所有外部依赖（Agent API、数据库），测试必须可独立运行

### Step 5: 验证验收标准
1. 逐条检查 Spec 第 4 节的验收标准
2. 如果涉及 UI，逐条检查 UX_TEST_SPEC.md 第 3 节的状态覆盖检查清单
3. 运行全量测试确保无回归
4. 确认没有遗漏后，输出完成报告：
   ```
   ## 模块开发完成
   - 模块: [名称]
   - Spec: docs/specs/[xxx]-spec.md
   - 验收标准: N/N 通过
   - UX 检查: N/N 通过
   - 测试: X passed, 0 failed
   - 下一步: 等待人工验收认可后进入 Step 6 Git 提交
   ```

### ⛔ Step 5.5: 人工验收闸门（硬性阻断）

**输出 Step 5 完成报告后，必须在此硬性停留，等待用户明确发出"人工验收认可"。**

- **通过口令**: 用户明确说 `人工验收认可` / `验收通过` / `批准提交` / `确认提交` 等确认性语句
- **拒绝口令**: 用户说 `驳回` / `修改` / `不通过` / `有问题` 等 → 回到对应 Step 修改
- **AI 行为**: 在此闸门处，AI 仅做以下事项：
  - 列出变更文件摘要（供用户审查）
  - 回答用户关于变更的任何问题
  - 根据用户反馈修改代码并重新运行测试
  - **绝对禁止**: 在未获得明确验收口令前执行任何 `git add`、`git commit`、`git push` 操作

### Step 6: Git 提交（仅限人工验收认可后执行）
1. 按 `docs/GIT_PROTOCOL.md` 第 10 节执行三关强制验证
2. Commit message 格式：`[ai] <type>: <描述>`
3. 每完成一个函数 = 一个 commit，不攒大 diff

## 禁止事项
- 不要在 Spec 没有覆盖的地方自行"补充"功能
- 不要跳过接口定义直接写实现
- 不要写完了才回头补测试——测试和实现一起提交
- 不要超出 Spec 第 6 节的 Non-Goals 范围
- 不要让 AI 等待中显示空白 UI——所有加载态必须有指示器
- **不要在未获得用户人工验收认可前执行任何 Git 提交操作**

## Phase 7D 审计 (2026-06-07)

- 引用仍有效：`docs/specs/`、`docs/TEST_PROTOCOL.md`、`docs/testing/UX_TEST_SPEC.md`、`docs/GIT_PROTOCOL.md`、`AGENTS.md` 均存在。
- 测试说明已从“内存数据库”修正为项目当前协议要求的真实迁移文件数据库。
- 新增提醒：IM 能力（置顶、归档、未读、免打扰、转发、多选）必须走真实 API/持久化状态；Reply/Pin 仍必须影响 Agent 上下文。

## Phase 9 审计 (2026-06-08)

- 引用仍有效：`docs/specs/phase9/README.md`、`docs/TEST_PROTOCOL.md`、`docs/GIT_PROTOCOL.md`、`AGENTS.md` 均存在。
- 流程补充：Phase 9 起模块开发必须同时验证 P1 local 零回归与 P2 cloud slice，不得只跑新增 cloud API 测试。
- 新增提醒：cloud Project 不能暴露本机或服务器物理路径；前端类型必须把 `workspacePath` 视为 local-only 可选字段，把 `workspaceId` 视为 cloud 主锚点。

## Phase 10 审计 (2026-06-08)

- 引用仍有效：`docs/specs/phase10/README.md`、`docs/deliverables/phase10-cloud-runtime/`、`docs/dev-logs/phase10-dev-log.md`、`docs/TEST_PROTOCOL.md`、`AGENTS.md` 均存在。
- 流程补充：开发 cloud runtime 时必须复用真实 CLI Adapter / RunService / ArtifactOutputBridge，不得新增裸 HTTP LLM 或 cloud-only MessageList 分支。
- 验证补充：Phase 10 起至少覆盖 sandbox ready、真实 CLI 输出、Artifact 创建、runtime logs 脱敏、配额阻断和 `runtime=local` 无 `sandboxId` 回归。

## Phase 14 审计 (2026-06-09)

- 引用仍有效：`docs/specs/phase14/README.md`、`docs/dev-logs/phase14-dev-log.md`、`docs/TEST_PROTOCOL.md`、`docs/GIT_PROTOCOL.md`、`AGENTS.md` 均存在。
- 流程补充：开发 SaaS/Mobile cloud API 时必须先确认 `TenantScope` / `TenantGuard` 契约，禁止只靠前端隐藏入口或请求参数声明租户。
- 验证补充：Phase 14 起生产 Auth 相关增量必须覆盖 dev header 禁用、401/403 边界、个人/团队 Project 列表过滤、viewer 写操作阻断和本地桌面端不强制登录。

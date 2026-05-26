---
name: agenthub-module-dev
description: AgentHub 项目标准模块开发流程。当用户要求开发新模块、新功能、新增量时触发。自动执行：读取对应 Spec → 确认接口契约 → 写实现 → 写单元测试 → 验证验收标准。
---

# AgentHub 标准模块开发流程

你正在 AgentHub 项目中进行模块开发。必须严格遵循以下流程，不可跳过任何步骤。

## 开发流程

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
5. 遵守 CLAUDE.md 中的所有代码规则（单文件 ≤ 300 行、禁止 any、async 等）

### Step 4: 写单元测试
1. 按照 `docs/TEST_PROTOCOL.md` 规范编写测试
2. 后端：pytest + httpx AsyncClient + 内存数据库，覆盖正常流程 + Spec 3.2 每个异常场景
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
   - 下一步: [建议的 Git commit 或下一个模块]
   ```

### Step 6: Git 提交
1. 按 `docs/GIT_PROTOCOL.md` 第 10 节执行三关强制验证
2. Commit message 格式：`[ai] <type>: <描述>`
3. 每完成一个函数 = 一个 commit，不攒大 diff

## 禁止事项
- 不要在 Spec 没有覆盖的地方自行"补充"功能
- 不要跳过接口定义直接写实现
- 不要写完了才回头补测试——测试和实现一起提交
- 不要超出 Spec 第 6 节的 Non-Goals 范围
- 不要让 AI 等待中显示空白 UI——所有加载态必须有指示器

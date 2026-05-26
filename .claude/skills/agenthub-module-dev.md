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

### Step 2: 确认接口契约
1. 检查 Spec 中定义的接口是否与 ADR-0005 中的契约一致
2. 如果本模块对外暴露新接口，先写接口定义（抽象类/类型），再写实现
3. 确认依赖的模块是否已就绪（Spec 第 5 节）

### Step 3: 写实现
1. 按照 Spec 的"不在范围内"清单，不写任何超出范围的功能
2. 后端：先写 Pydantic schema → 再写 Service → 最后写 API 路由
3. 前端：先写类型定义 → 再写 Store → 最后写组件
4. 遵守 CLAUDE.md 中的所有代码规则（单文件 ≤ 300 行、禁止 any、async 等）

### Step 4: 写单元测试
1. 后端：pytest + httpx AsyncClient，覆盖正常流程 + 每个异常场景
2. 前端：Vitest，覆盖组件渲染 + Store 逻辑
3. 测试用例直接对应 Spec 第 3 节的每个场景

### Step 5: 验证验收标准
1. 逐条检查 Spec 第 4 节的验收标准
2. 手动运行 `npm run dev` + `uvicorn main:app` 验证可演示
3. 确认没有遗漏后，输出完成报告：
   ```
   ## 模块开发完成
   - 模块: [名称]
   - Spec: docs/specs/[xxx]-spec.md
   - 验收标准: N/N 通过
   - 测试: X passed, 0 failed
   - 下一步: [建议的下一个模块或提交 commit]
   ```

## 禁止事项
- 不要在 Spec 没有覆盖的地方自行"补充"功能
- 不要跳过接口定义直接写实现
- 不要写完了才回头补测试——测试和实现一起提交
- 不要超出 Spec 第 6 节的 Non-Goals 范围

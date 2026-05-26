---
name: agenthub-phase-wrapup
description: AgentHub 阶段收尾标准流程。当用户说"阶段验收通过"、"收尾"、"phase wrap-up"或准备进入下一阶段时触发。自动执行：文档审计 → 开发日志 → 下阶段文档 → Skill 审计 → 资产沉淀 → Git 提交。
---

# AgentHub 阶段收尾标准流程

你正在对 AgentHub 项目进行阶段收尾。按以下 6 步执行，不可跳过。

---

## Step 1: 文档审计与重组

### 1.1 全量文档扫描
- 读取 `docs/` 下所有 `.md` 文件
- 读取 `.claude/skills/` 下所有 skill 文件
- 读取项目根目录 `CLAUDE.md`、`CONTEXT.md`
- 读取 `.trae/rules/` 下的规则文件

### 1.2 交叉引用分析
- 构建完整引用图：每个文档链接了哪些其他文档？
- 标记循环引用
- 标记"指向不存在文件"的过时引用

### 1.3 重复与矛盾检测
- 哪些规则在多个文件中重复定义？
- 哪些配置描述与实际文件不一致？（如 `.gitignore` 内容）
- 哪些测试计划引用了不存在的测试文件？

### 1.4 执行修复
- 去重：让一个文件成为权威来源，其他文件引用它
- 修复矛盾：统一配置描述与实际文件
- 精简：删除冗余内容，合并可合并的文档
- 更新引用：修复过时链接和引用路径

### 1.5 交付物
- 在本阶段 spec 文件末尾追加「Phase N 文档审计记录」段落
- 列出发现的问题和已执行的修复

---

## Step 2: 撰写阶段开发日志

### 2.1 日志结构

创建 `docs/phase{N}-dev-log.md`，包含：

```markdown
# Phase N 开发日志：[阶段名称]

## 1. 阶段概述
- 交付成果表（模块、内容、规模）
- 与 Spec 验收标准的对应关系

## 2. 开发时间线
- 按 Day 0 → Day N 的时间顺序
- 每天标注完成的关键任务

## 3. 遇到的 Bug 与解决方案
- 每个 Bug：现象 → 根因 → 解决 → 教训
- 重点记录"如果重来一次应该怎么做"

## 4. 建立的基础设施
- 规范文档、测试套件、工具链、自动化

## 5. 关键方法总结
- Vibe Coding 心得
- AI 协作心得
- 项目治理心得

## 6. 下一步
- 下个阶段的核心目标和待办事项
```

### 2.2 交付物
- `docs/phase{N}-dev-log.md`

---

## Step 3: 准备下一阶段文档

### 3.1 创建下一阶段 Spec（草稿）

基于本阶段成果和 ADR-0005 的架构演进计划，创建 `docs/specs/phase{N+1}-xxx-spec.md`：

- 目标：下个阶段要打通什么？
- 输入输出：新增/修改的 API 端点、数据模型、接口定义
- 行为规格：正常流程、异常流程、边界条件
- 验收标准
- 依赖状态
- 不在范围内（Non-Goals）

### 3.2 更新 CONTEXT.md

- 更新「当前开发阶段」指向新 Phase
- 更新 Key Documents 索引表，添加新的 Spec 和文档

### 3.3 更新 CLAUDE.md

- 更新「Phase Awareness」中的当前阶段信息
- 更新范围说明

### 3.4 交付物
- `docs/specs/phase{N+1}-xxx-spec.md` (Draft)
- 更新后的 CONTEXT.md
- 更新后的 CLAUDE.md

---

## Step 4: Skill 审计与更新

### 4.1 审计现有 Skills

检查 `.claude/skills/` 下的每个 skill：
- 是否引用了仍存在的文件？
- 检查清单是否覆盖了新协议的要求？
- 流程步骤是否仍然有效？
- 禁止事项是否需要补充？

### 4.2 更新优先级

| 优先级 | 情况 | 操作 |
|--------|------|------|
| 高 | Skill 引用的文件已重命名/删除 | 立即修复引用 |
| 中 | Skill 缺少新协议的检查项 | 追加新检查项 |
| 低 | Skill 措辞可改进 | 下个阶段迭代 |

### 4.3 交付物
- 审计报告（在每个 skill 文件底部追加 `## Phase N 审计 (YYYY-MM-DD)` 段落）
- 更新后的 skill 文件

---

## Step 5: 可沉淀资产检查

### 5.1 候选 Skill 识别

扫描本阶段的开发过程，识别值得沉淀为 Skill 的模式：

- 是否有反复执行的标准化操作流程？
- 是否有"如果有个 skill 就不用每次重做"的痛点？
- 是否有通用的项目级检查逻辑？

### 5.2 候选 Rule 识别

扫描本阶段的代码改动，识别值得沉淀为 Rule 的约束：

- 是否有反复出现的代码模式？（如 SSE 事件序列化、StreamingResponse 校验）
- 是否有本阶段踩过、下阶段可能再踩的坑？
- 是否有需要全局强制的新禁止事项？

### 5.3 决策

- 如果有值得沉淀的 → 创建对应 Skill/Rule 文件
- 如果没有 → 在收尾报告中明确写"本阶段无可沉淀资产"

---

## Step 6: Git 操作

### 6.1 提交本阶段收尾变更

```
按 GIT_PROTOCOL.md 三关验证后提交：
- docs/ 下的文档变更
- .claude/skills/ 下的 skill 更新
- CONTEXT.md / CLAUDE.md 更新
```

### 6.2 Phase 完成合并

```
1. git checkout phase/phase{N}-xxx
2. 确认所有 PR 已合并
3. 全量测试通过
4. git checkout main
5. git merge --no-ff phase/phase{N}-xxx
6. git tag -a v0.{N}.0 -m "Phase N: [阶段名称]"
7. git push origin main --tags
```

---

## 收尾完成报告

全部 6 步完成后，输出：

```
## Phase N 收尾完成

### 文档审计
- 发现问题: X 处
- 修复: X 处
- 文档数量: 从 N 个精简到 M 个

### 开发日志
- 文件: docs/phase{N}-dev-log.md
- 记录 Bug: X 个
- 沉淀方法: X 条

### 下阶段准备
- Spec: docs/specs/phase{N+1}-xxx-spec.md (Draft)
- CONTEXT.md: 已更新
- CLAUDE.md: 已更新

### Skill 审计
- 审计 skill: X 个
- 更新: X 个
- 新建: X 个

### 资产沉淀
- 新 Skill: [列表] (如果无: 本阶段无可沉淀资产)
- 新 Rule: [列表] (如果无: 本阶段无可沉淀规则)

### Git
- Commit: X 个
- Tag: v0.{N}.0
- 推送: origin/main ✓
```

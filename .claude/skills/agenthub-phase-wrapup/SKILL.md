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
- 读取 `.agents/skills/` 下所有 skill 文件；若 `.claude/skills/` 存在同名镜像，也要同步审计
- 读取项目根目录 `AGENTS.md`、`CLAUDE.md`、`CONTEXT.md`
- 读取 `.trae/rules/` 下的规则文件

### 1.2 交叉引用分析
- 构建完整引用图：每个文档链接了哪些其他文档？
- 标记循环引用
- 标记"指向不存在文件"的过时引用

### 1.3 重复与矛盾检测
- 哪些规则在多个文件中重复定义？
- 哪些配置描述与实际文件不一致？（如 `.gitignore` 内容）
- 哪些测试计划引用了不存在的测试文件？

### 1.4 渐进式披露检查
- 每个事实是否有唯一的权威源？（禁止跨文档复制粘贴）
- 文档层级是否清晰：入口层(CLAUDE/CONTEXT) → 决策层(ADR) → 规格层(Spec) → 协议层(Protocol) → 记录层(Dev Log)
- 新内容是否归入了已有文档？（先考虑补充现有文档，再考虑新建）
- 跨文档引用是否用链接而非复制？（见 CLAUDE.md Documentation Rules）

### 1.5 执行修复
- 去重：让一个文件成为权威来源，其他文件引用它
- 修复矛盾：统一配置描述与实际文件
- 精简：删除冗余内容，合并可合并的文档
- 更新引用：修复过时链接和引用路径

### 1.6 交付物
- 在本阶段 spec 文件末尾追加「Phase N 文档审计记录」段落
- 列出发现的问题和已执行的修复

---

## Step 2: 撰写阶段开发日志

### 2.1 日志结构

创建 `docs/dev-logs/phase{N}-dev-log.md`，包含：

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
- `docs/dev-logs/phase{N}-dev-log.md`

---

## Step 3: Skill 审计与更新

### 3.1 审计现有 Skills

检查 `.agents/skills/` 下的每个 skill；若 `.claude/skills/` 存在同名镜像，也要同步检查：
- 是否引用了仍存在的文件？
- 检查清单是否覆盖了新协议的要求？
- 流程步骤是否仍然有效？
- 禁止事项是否需要补充？

### 3.2 更新优先级

| 优先级 | 情况 | 操作 |
|--------|------|------|
| 高 | Skill 引用的文件已重命名/删除 | 立即修复引用 |
| 中 | Skill 缺少新协议的检查项 | 追加新检查项 |
| 低 | Skill 措辞可改进 | 下个阶段迭代 |

### 3.3 交付物
- 审计报告（在每个 skill 文件底部追加 `## Phase N 审计 (YYYY-MM-DD)` 段落）
- 更新后的 skill 文件

---

## Step 4: 可沉淀资产检查

### 4.1 候选 Skill 识别

扫描本阶段的开发过程，识别值得沉淀为 Skill 的模式：

- 是否有反复执行的标准化操作流程？
- 是否有"如果有个 skill 就不用每次重做"的痛点？
- 是否有通用的项目级检查逻辑？

### 4.2 候选 Rule 识别

扫描本阶段的代码改动，识别值得沉淀为 Rule 的约束：

- 是否有反复出现的代码模式？（如 SSE 事件序列化、StreamingResponse 校验）
- 是否有本阶段踩过、下阶段可能再踩的坑？
- 是否有需要全局强制的新禁止事项？

### 4.3 决策

- 如果有值得沉淀的 → 创建对应 Skill/Rule 文件
- 如果没有 → 在收尾报告中明确写"本阶段无可沉淀资产"

---

## 收尾完成报告

全部 4 步完成后，输出：

```
## Phase N 收尾完成

### 文档审计
- 发现问题: X 处
- 修复: X 处
- 文档数量: 从 N 个精简到 M 个

### 开发日志
- 文件: docs/dev-logs/phase{N}-dev-log.md
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
```

## Phase 7D 审计 (2026-06-07)

- 引用修复：主 Skill 目录以 `.agents/skills/` 为准，`.claude/skills/` 作为镜像同步审计对象。
- 阶段收尾本轮新增文档入口：`docs/deliverables/phase7-im-hardening/`。
- 暂不新建 Skill/Rule：本轮 IM 能力属于 Phase 7D 规格内实现，现有 module-dev / code-review / qa-audit / phase-wrapup 四个 Skill 已能覆盖；后续若多次重复做“IM 真实服务截图审计”，再考虑单独沉淀。

## Phase 9 审计 (2026-06-08)

- 引用仍有效：`.agents/skills/` 与 `.claude/skills/` 镜像均存在，`docs/specs/phase9/README.md`、`docs/deliverables/phase9-cloud-workspace/`、`docs/dev-logs/phase9-dev-log.md` 已作为本阶段文档入口。
- 阶段收尾新增硬口径：P2 SaaS 阶段的完成报告必须同时写出 P1 local 零回归与当前 cloud slice 真实服务结果。
- 暂不新建独立 Skill/Rule：Phase 9 的可复用经验已并入 module-dev / code-review / qa-audit / phase-wrapup；若 Phase 10-11 多次重复 cloud runtime 验收脚本，再考虑沉淀专门 Skill。

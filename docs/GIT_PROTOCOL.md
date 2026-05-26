# Git 协作规范

**版本**: v1.0
**创建日期**: 2026-05-26
**适用范围**: AgentHub 所有开发者（人类 + AI Agent）

---

## 1. 核心理念

> **每个 commit 都是可独立 review、可安全 revert、可通过测试的最小单元。**

这不是追求"小"的洁癖——小 commit 意味着：
- 出问题时 `git bisect` 能精确到一行代码
- Code review 可以在 5 分钟内完成（而不是 30 分钟翻几百行 diff）
- revert 一个 bug 不会连带丢掉正常功能

---

## 2. 分支策略

### 2.1 分支模型

```
main ─────────────────────────────────────────────────────▶
  │
  ├── phase/phase1-walking-skeleton ──── (当前)
  │       └── feat/xxx
  │       └── fix/xxx
  │
  ├── phase/phase2-xxx ──── (未来)
  │
  └── hotfix/xxx ──── (紧急修复，直接基于 main)
```

### 2.2 分支类型

| 分支前缀 | 用途 | 命名示例 | 生命周期 |
|---------|------|---------|---------|
| `phase/` | 阶段性开发主线（长期分支） | `phase/phase1-walking-skeleton` | 整个 Phase |
| `feat/` | 新功能开发（基于 `phase/` 分支） | `feat/sse-chat-endpoint` | 1-3 天 |
| `fix/` | Bug 修复 | `fix/sse-json-single-quotes` | 几小时-1 天 |
| `refactor/` | 重构（不改变行为） | `refactor/extract-chat-service` | 1-2 天 |
| `docs/` | 文档变更 | `docs/test-protocol` | 几小时 |
| `hotfix/` | 紧急修复（基于 `main`） | `hotfix/api-key-leak` | 几小时 |

### 2.3 分支生命周期

```
1. 从 phase/ 分支切出 feat/ 或 fix/
2. 本地开发 → 小 commit 迭代
3. 推到远程 → 创建 PR → Code Review
4. 合并到 phase/ 分支（squash 或 rebase）
5. 删除 feat/fix 分支

Phase 完成时:
6. phase/ 分支合并到 main（保留完整 history，merge commit）
7. 在 main 上打 tag
```

---

## 3. Commit 规范

### 3.1 粒度铁律

**每个 commit 只做一件事，且做到可运行。**

```
✅ 好的 commit:
  - "feat: POST /api/sessions/{id}/chat 端点 SSE 流式响应"
  - "fix: SSE JSON 使用 json.dumps 替代 !r 格式化"
  - "test: 新增 Chat API 11 条测试用例"
  - "docs: 添加 UX 交互体验测试规范"

❌ 坏的 commit:
  - "WIP" / "save work" / "update"
  - "完成了聊天功能、修复了bug、更新了文档"（三件事混一起）
  - "refactor: 重写了所有模块"（太大，不可 review）
```

### 3.2 提交格式

```
<type>: <简短描述>

[可选：为什么这个变更是有必要的]

关联: #[issue号]
```

**type 类型**：

| Type | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: 实现 POST /api/sessions 端点` |
| `fix` | Bug 修复 | `fix: 修复空消息导致 500 的问题` |
| `refactor` | 重构（不改行为） | `refactor: 校验逻辑从 generator 移到路由层` |
| `test` | 测试 | `test: 新增 SSE JSON 合法性回归测试` |
| `docs` | 文档 | `docs: 起草 Git 协作规范` |
| `chore` | 杂项（依赖、配置） | `chore: Python venv 升级到 3.12` |
| `style` | 格式（空格、命名） | `style: 统一使用双引号` |

### 3.3 提交频率

```
每完成一件事 = 一次 commit:
  - 写了一个函数 → commit
  - 写了一个测试 → commit
  - 修复了一个 lint 警告 → commit
  - 更新了一个文档段落 → commit
```

**不要攒一堆改动一次 commit。** 一天提交 20 次比一周提交 1 次好得多。

---

## 4. Pull Request 规范

### 4.1 PR 模板

```markdown
## 概述
<一句话描述这个 PR 做了什么>

## 变更清单
- [ ] feat: xxx
- [ ] test: xxx

## 验证
- [ ] pytest 全量通过 (28/28)
- [ ] TypeScript 编译零错误
- [ ] UX 检查清单通过（如涉及前端）

## 截图（如涉及 UI）
<截图>
```

### 4.2 PR 大小限制

| 指标 | 上限 |
|------|------|
| 单 PR 文件数 | ≤ 10 |
| 单 PR 新增行数 | ≤ 500 |
| 单 PR 描述长度 | ≥ 50 字 |

超过上限时，拆分为多个 PR。大重构用 `refactor/` 分支 + 多人 review。

### 4.3 Review 规则

- **至少 1 人 approve** 才能合并（AI agent 提交的代码由人类 review）
- Review 关注：逻辑正确性、安全（API Key 泄露、SQL 注入）、代码规范
- Review 24 小时内完成（Phase 内的小 PR）
- **Review 通过后由作者自己 merge**（不是 reviewer merge）

---

## 5. Merge 策略

| 场景 | 策略 | 原因 |
|------|------|------|
| `feat/` → `phase/` | **Squash & Merge** | 保持 phase 分支历史干净 |
| `phase/` → `main` | **Merge Commit** | 保留 Phase 级别的完整历史 |
| `hotfix/` → `main` | **Merge Commit** | 紧急修复必须可追溯 |
| `main` 回退到 `phase/` | **Merge main → phase/** | 同步 hotfix 到开发分支 |

---

## 6. Tag 与版本

### 6.1 Tag 命名

```
v<主版本>.<阶段号>.<补丁号>

v0.1.0  ← Phase 1 完成
v0.2.0  ← Phase 2 完成
v0.1.1  ← Phase 1 的 hotfix
v1.0.0  ← MVP 首次发布
```

### 6.2 Tag 时机

- 每个 Phase 完成、合并到 `main` 后 → 立即打 tag
- Tag 信息写明 Phase 范围和关键交付物清单
- **不要在 phase 分支内打 tag**

### 6.3 Tag 示例

```bash
git tag -a v0.1.0 -m "Phase 1: 行走骨架 — 单聊全链路 SSE 流式对话"
```

---

## 7. .gitignore 规范

当前 `.gitignore` 已在用，后续 Phase 按需追加：

```gitignore
# === 环境 & 密钥（绝对不能提交） ===
.env
.env.*
!.env.example
*.pem
*.key
credentials.*

# === Python ===
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/

# === Node ===
node_modules/
.next/
dist/

# === IDE ===
.vscode/settings.json
.idea/
*.swp
*.swo

# === 数据库 ===
*.db
*.sqlite
*.sqlite3

# === OS ===
.DS_Store
Thumbs.db
Desktop.ini

# === 临时文件 ===
*.tmp
*.log
.trae/
```

---

## 8. 常见场景操作指南

### 8.1 开始新功能

```bash
git checkout phase/phase1-walking-skeleton
git pull
git checkout -b feat/my-new-feature
# 开发 → 多次 commit → 推送到远程
git push -u origin feat/my-new-feature
# 在 GitHub 创建 PR → base: phase/phase1-walking-skeleton
```

### 8.2 Phase 完成合并

```bash
# 1. 确保 phase 分支所有 PR 已合并
git checkout phase/phase1-walking-skeleton
git pull

# 2. 运行全量测试
cd backend && pytest test_api/ test_smoke.py -q
cd frontend && npx tsc --noEmit && npx vitest run

# 3. 合并到 main
git checkout main
git merge --no-ff phase/phase1-walking-skeleton -m "merge: Phase 1 行走骨架完成"

# 4. 打 tag
git tag -a v0.1.0 -m "Phase 1: 行走骨架"

# 5. 推送
git push origin main --tags
```

### 8.3 紧急 Hotfix

```bash
git checkout main
git checkout -b hotfix/urgent-fix
# 修复 → commit → push → PR
# 合并到 main 后:
git checkout phase/phase1-walking-skeleton
git merge main  # 同步 hotfix 到开发分支
```

### 8.4 撤销错误 commit（未推送）

```bash
# 保留改动在工作区（推荐）
git reset --soft HEAD~1

# 完全丢弃
git reset --hard HEAD~1
```

**已推送的 commit 不要 reset，用 `git revert`。**

---

## 9. AI Agent 提交规则

本项目的代码多数由 Claude Agent 生成。AI 提交有以下附加规则：

- AI 提交的 commit message 必须带 `[ai]` 前缀（方便人类快速识别）：`[ai] feat: xxx`
- AI 不得执行 `git push --force`、`git reset --hard`（除非人类明确指令）
- AI 提交前必须完成：代码编译检查、相关测试通过
- 人类最终 review 并 merge

---

## 10. 检查清单

每次提交前：

- [ ] 提交粒度合理（一件事，一个 commit）
- [ ] Commit message 格式正确（type: 描述）
- [ ] 没有提交 `.env`、`node_modules`、`__pycache__` 等
- [ ] 关联测试通过
- [ ] 如果是 bug 修复，有回归测试

---

## 11. 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本，定义分支策略、Commit 规范、PR 流程、AI 提交规则 |

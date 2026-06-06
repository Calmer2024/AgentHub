# Phase 7D IM 体验与 UI 加固验收日志

**日期**: 2026-06-07
**结论**: 自动化覆盖已补齐并通过；真实服务视觉验收建议继续补充记录

## 1. 本轮人工需求对应关系

| 需求 | 实现状态 | 证据 |
|------|----------|------|
| 会话列表支持新建、置顶、归档、搜索、最近活跃排序 | 已实现 | `SessionList.tsx`、`SessionService.list_sessions()` |
| 置顶像微信一样独立明显，并移动到第一组 | 已实现 | 置顶区、置顶徽标、后端排序 |
| 归档像 Telegram 一样顶部归档文件夹 | 已实现 | 归档入口与归档箱视图 |
| 未读数、免打扰、多选、转发 | 已实现 | 迁移 018、转发 API、前端多选/转发弹窗 |
| 消息右键菜单动画 | 已实现 | `agenthub-popover` 动画与 portal 菜单 |
| 右键操作影响 Agent 交互 | 已实现/保持 | Reply 和 Pin 仍走真实上下文注入；转发创建真实消息 |
| 每个气泡下方显示完整时间戳 | 已实现 | `formatChinaFullDateTime()` |
| Agent 名称去绿点与边框，独立颜色加粗 | 已实现 | `MessageBubble.tsx` 与 CSS |
| 执行过程全屏弹窗 | 已实现 | `ExecutionTracePanel.tsx` |
| 明亮主题辅色改纯白、布局卡片化 | 已实现 | `index.css`、`App.tsx`、相关组件样式 |

## 2. 自动化测试覆盖

本轮回归命令：

```powershell
cd backend
python -m pytest test_unit/ test_api/ -q

cd frontend
npx tsc --noEmit
npx vitest run
npm run build
```

执行结果：

- Backend: 272 passed
- Frontend typecheck: passed
- Frontend tests: 14 files / 70 tests passed
- Frontend build: passed；Vite 仅提示部分 chunk 超过 500 kB

本轮新增/更新测试覆盖：

- `SessionList.test.tsx`：置顶排序、未读/免打扰、归档箱和取消归档；
- `MessageActions.test.tsx`：右键菜单项、转发、多选；
- `MessageBubble.test.tsx`：右键菜单、选择控件、完整时间戳和 Agent 名称样式；
- `ChatWindow.test.tsx`：转发入口 mock 与原有停止回退；
- `test_session_service.py` / `test_sessions.py`：pin/archive/mute/read/forward；
- `test_migrations.py`：会话 IM 状态字段迁移。

## 3. 建议继续补充的真实服务视觉验收

v1.0 基线已通过自动化回归。后续建议在真实服务上继续确认：

- 明亮主题下项目栏、聊天栏、文件视图、输入框外层均符合纯白/透明要求；
- 会话置顶后立刻进入置顶区，刷新后仍保持；
- 归档后会话进入归档箱，归档箱内可取消归档；
- 免打扰后未读徽标弱化；
- 消息右键菜单不会被下方会话或滚动区域遮挡；
- 单条转发和多选转发能在目标会话中出现真实消息；
- 执行过程全屏弹窗可打开、滚动、关闭。

## 4. 剩余风险

- 完整真实 Claude Code 演示脚本仍未沉淀为自动化 E2E；
- `ChatWindow` 和 `SessionList` 继续承载较多交互状态，后续可继续按 domain store 拆分；
- 未读计数当前以服务端写入消息时累加，跨设备实时通知与免打扰推送策略属于后续增强；
- 转发目前以文本消息快照落库，附件/Artifact 级联转发仍是后续范围。

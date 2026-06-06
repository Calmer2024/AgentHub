# Phase 7D IM 体验与 v1.0 UI 加固交付文档

**日期**: 2026-06-07
**范围**: 会话列表 IM 能力、消息右键菜单、转发/多选、未读/免打扰、明亮主题与卡片化布局、执行过程全屏查看
**状态**: v1.0 基线已实现，自动化回归通过；真实 Claude Code 完整 E2E 待后续沉淀

本目录记录 Phase 7D 本轮 IM 体验加固的交付快照。长期规格仍以 [Phase 7 Spec](../../specs/phase7/README.md) 和 [Phase 7D Spec](../../specs/phase7/04-mvp-demo-ux-hardening.md) 为准；这里面向验收、交接和 v1.0 发布说明。

## 交付清单

| 文档 | 作用 |
|------|------|
| [implementation-snapshot.md](implementation-snapshot.md) | 说明会话 pin/archive/unread/mute/forward API、前端会话列表、消息菜单、视觉主题和执行过程全屏的实际落点。 |
| [acceptance-log.md](acceptance-log.md) | 记录本轮自动测试覆盖、建议继续补充的真实服务视觉验收和剩余风险。 |
| [../../dev-logs/phase7-dev-log.md](../../dev-logs/phase7-dev-log.md) | Phase 7 开发日志：7A-7C 运行控制与 7D IM 加固的连续记录。 |

## 本轮结论

Phase 7D 将 AgentHub 的聊天体验从“能发消息的开发工具界面”推进到更接近 IM 软件的 v1.0 基线：

```text
项目栏 + 好友栏
  -> 对话列表支持搜索、置顶、归档箱、未读数、免打扰、最近活跃排序
  -> 消息气泡支持右键菜单、引用、Pin、转发、多选、完整时间戳
  -> 转发写入真实消息并保留来源快照
  -> 明亮主题收敛为纯白辅色和圆角卡片布局
  -> 执行过程可全屏查看
```

本轮新增能力都尽量落在真实数据模型与 API 上，而不是只做前端静态状态：会话置顶/归档/未读/免打扰持久化在 `sessions` 表；转发通过 `/api/sessions/forward` 创建真实消息；已读通过 `/api/sessions/{id}/read` 清零。

## 后续入口

- 自动化回归已通过：`pytest test_unit/ test_api/ -q`、`npx tsc --noEmit`、`npx vitest run`、`npm run build`。
- 建议继续补一轮真实服务视觉验收：启动当前仓库后端/前端，检查会话列表、右键菜单、转发、多选、全屏执行过程、文件卡片布局和明亮主题视觉。
- 真实 Claude Code 完整 E2E 脚本仍是后续沉淀项，不在本轮文档中伪装为已自动化完成。

# Phase 7 Runtime Control / Approval / Health 交付文档

**日期**: 2026-06-06
**范围**: Phase 7A-7C，运行任务可控性、人工审批断点、环境体检
**状态**: 本轮验收通过

本目录记录 Phase 7A-7C 的交付快照。长期规格仍以 [Phase 7 Spec](../../specs/phase7/README.md) 为准；这里面向验收、交接和后续 Phase 7D 接续开发。

## 交付清单

| 文档 | 作用 |
|------|------|
| [implementation-snapshot.md](implementation-snapshot.md) | 说明本轮后端 run/approval/health 服务、API、SSE 事件、前端控制条/审批卡/体检卡和取消回退的实际落点。 |
| [acceptance-log.md](acceptance-log.md) | 记录自动测试、人工验收结论、取消缺陷修复和剩余风险。 |
| [../../dev-logs/phase7-dev-log.md](../../dev-logs/phase7-dev-log.md) | Phase 7 开发日志：完成事项、关键决策、验收缺陷与交接入口。 |

## 本轮结论

Phase 7A-7C 已打通核心闭环：

```text
用户发送任务
  -> 后端创建 run/task/process
  -> 前端 RuntimeControlStrip 展示运行状态
  -> 用户可停止本次输出
  -> 后端终止进程并持久化 cancelled 状态
  -> 需要确认时创建 ApprovalCheckpoint
  -> ApprovalCard 在消息下方确认/驳回
  -> 发送前 SystemHealthService 阻断不可执行环境
```

人工验收已确认：停止本次输出后有明确中止成功消息，输入框恢复可用，当前会话和其它会话不会继续被全局 streaming 状态占用。

## 后续入口

- Phase 7D 继续补真实 Claude Code 演示脚本、截图审计和 E2E 验收矩阵。
- Store 仍可进一步按 `runtimeStore`、`approvalStore`、`systemStore` 拆分；当前实现已满足 7A-7C 功能验收，但仍有后续架构整理空间。
- 审批“释放下游任务”在当前实现中完成状态机与 API 基线，完整 Orchestrator scheduler 释放链路留给后续调度增强。

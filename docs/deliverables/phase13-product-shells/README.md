# Phase 13 多端产品壳拆分交付文档

**日期**: 2026-06-09  
**范围**: Local Desktop Shell、SaaS Web Shell、Mobile Shell、`/api/capabilities` 能力矩阵、三端构建命令、Tauri/Capacitor skeleton、真实服务验收  
**状态**: 已实现，自动化回归与真实服务验收通过；Git 提交等待人工验收确认

本目录记录 Phase 13 的交付快照。长期规格以 [Phase 13 Spec](../../specs/phase13/README.md) 为准；这里面向验收、交接和后续产品壳迭代。

## 交付清单

| 文档 | 作用 |
|------|------|
| [implementation-snapshot.md](implementation-snapshot.md) | 说明能力契约、三端前端入口、移动壳、Artifact 动作门禁和 native skeleton 的实际落点。 |
| [acceptance-log.md](acceptance-log.md) | 记录自动化测试、三端构建、真实服务轮换验收、截图和剩余边界。 |
| [../../dev-logs/phase13-dev-log.md](../../dev-logs/phase13-dev-log.md) | Phase 13 开发日志：时间线、关键修复、测试矩阵和后续建议。 |

## 本轮结论

Phase 13 已把 Phase 9-12 积累出的本地版、SaaS 版和移动端能力从“一个混合 React 壳”拆成三个可独立启动和验收的产品入口：

```text
RuntimeCapabilities
  -> AppRoot / ShellProvider
  -> LocalDesktopShell | SaasWebShell | MobileShell
  -> capability-gated feature actions
  -> independent dev/build scripts
```

本地版只暴露本机项目、本机 CLI、本地 preview/build/export。SaaS 版暴露个人空间/团队、cloud workspace、preview/deployment、协作通知和云端设置。Mobile Shell 使用单列触控布局，只承载会话、通知、审批和 Artifact 查看。

## 验收入口

- 后端全量 API：`cd backend && .\venv\Scripts\python.exe -m pytest test_api/ -q`
- 后端单元：`cd backend && .\venv\Scripts\python.exe -m pytest test_unit/ -q`
- 前端类型：`cd frontend && npx tsc --noEmit`
- 前端单测：`cd frontend && npx vitest run`
- 三端构建：`npm run build:local`、`npm run build:saas`、`npm run build:mobile`
- 壳 smoke：`cd desktop && node scripts/smoke.mjs`、`cd mobile && node scripts/smoke.mjs`
- 真实服务访问：
  - 前端：`http://127.0.0.1:5173/`
  - 后端：`http://127.0.0.1:8000/`
  - API Docs：`http://127.0.0.1:8000/docs`

## 并行启动

仓库根目录提供三端并行启动器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-three-shells.ps1
```

默认端口矩阵：

| 端 | 前端 | 后端 |
|----|------|------|
| Local Desktop | `http://127.0.0.1:5173` | `http://127.0.0.1:8000` |
| SaaS Web | `http://127.0.0.1:5174` | `http://127.0.0.1:8010` |
| Mobile | `http://127.0.0.1:5175` | `http://127.0.0.1:8020` |

停止三端：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop-three-shells.ps1
```
  - 能力矩阵代理：`http://127.0.0.1:5173/api/capabilities`

# Phase 10 Sandbox Runner 与云端 Agent Runtime 验收日志

**日期**: 2026-06-08  
**结论**: Phase 10 自动化验收与真实服务 smoke 均通过；P1 本地版与 P2 cloud runtime 切片未发现回归。

## 自动化验收

| 验收项 | 结果 | 证据 |
|--------|------|------|
| cloud Project 发送消息创建 sandbox 并启动真实 CLI | 通过 | `backend/test_api/test_phase10_cloud_runtime.py` |
| CLI 写入 cloud workspace 后创建消息级 Artifact | 通过 | `WRITE_HTML_ARTIFACT` fixture + `/api/sessions/{id}/artifacts` |
| runtime logs 查询与 Secret 脱敏 | 通过 | `/api/runs/{runId}/logs` 不含原始 Secret，包含 `[REDACTED]` |
| sandbox stopped 后 workspace snapshot 仍可用 | 通过 | 停止 sandbox 后调用 `/api/workspaces/{id}/snapshots` |
| sandbox 并发配额阻断 | 通过 | 第三个 active sandbox 返回 409 |
| 显式 local runtime 不要求 sandbox | 通过 | `runtime = "local"` 返回 `sandboxId = null` |
| Phase 9 cloud workspace 回归 | 通过 | `pytest backend/test_api/test_phase9_cloud_workspace.py -q` |
| 后端全量 API / unit | 通过 | `172 passed`、`160 passed` |
| 前端类型与全量 vitest | 通过 | `npx tsc --noEmit`、`92 passed` |
| 真实服务基础路径 | 通过 | 后端 `/`、`/docs`；前端 `/`；Vite `/api/quotas/me` 代理均返回 200 |
| 真实服务 cloud runtime | 通过 | 通过前端 `/api` 代理完成 cloud Project、Secret、chat、Artifact、logs 脱敏 |
| 真实服务取消 | 通过 | `SLEEP` fixture run 经 `/api/runs/{runId}/cancel` 变为 `cancelled` |
| 浏览器截图审计 | 通过 | `backend/venv/Scripts/python.exe e2e/phase8_screenshot_audit.py` |

## 最终复验

2026-06-08 最终重启当前代码服务后，再次通过前端 `/api` 代理执行真实 HTTP smoke：

- 基础路径：后端 `/` = 200，后端 `/docs` = 200，前端 `/` = 200。
- 云端运行：`runId = a18eec7e-9c15-4641-9283-0e7a55174f6c`，`sandboxId = 568d0362-dc1a-4795-9623-15b2e99c950f`。
- 产物：cloud CLI 写出 `index.html` 并被 Artifact Bridge 收集。
- Secret：SSE 与 `/api/runs/{runId}/logs` 均不包含原始 `PHASE10_TOKEN`，只出现 `[REDACTED]`。
- 本地模式：显式 `runtime = "local"` 返回 `sandboxId = null`，本地版不进入 cloud sandbox。

## 已执行命令

```powershell
pytest backend/test_api/test_phase9_cloud_workspace.py -q
pytest backend/test_api/test_phase10_cloud_runtime.py -q
pytest backend/test_api -vv --maxfail=1
pytest backend/test_unit -q
cd frontend; npx tsc --noEmit
cd frontend; npx vitest run
backend/venv/Scripts/python.exe e2e/phase8_screenshot_audit.py
```

## 真实服务地址

- 前端：`http://127.0.0.1:5173/`
- 后端：`http://127.0.0.1:8000/`
- API Docs：`http://127.0.0.1:8000/docs`

## 风险与后续

- 当前 runner 是本机隔离目录 + subprocess 的可替换切片，生产 SaaS 仍需 Docker/microVM、对象存储和正式网络策略。
- Secret 加密为开发态可逆实现，生产需接 KMS/密钥轮换。
- 云端 preview/deployment 仍在 Phase 11，不应把 Phase 10 当作完整 SaaS IDE。

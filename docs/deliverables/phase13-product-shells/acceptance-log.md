# Phase 13 验收日志

**日期**: 2026-06-09  
**状态**: 自动化回归与真实服务验收通过；等待人工验收后才允许 Git 提交

## 自动化回归

| 命令 | 结果 |
|------|------|
| `cd backend && .\venv\Scripts\python.exe -m pytest test_api/ -q` | 180 passed |
| `cd backend && .\venv\Scripts\python.exe -m pytest test_unit/ -q` | 160 passed |
| `cd frontend && npx tsc --noEmit` | passed |
| `cd frontend && npx vitest run` | 17 files / 101 tests passed |
| `cd frontend && npm run build:local` | passed，输出 `dist-local/` |
| `cd frontend && npm run build:saas` | passed，输出 `dist-saas/` |
| `cd frontend && npm run build:mobile` | passed，输出 `dist-mobile/` |
| `cd desktop && node scripts/smoke.mjs` | `AgentHub local desktop shell smoke OK` |
| `cd mobile && node scripts/smoke.mjs` | `AgentHub mobile shell smoke OK` |

说明：Vite 构建仍有既有大 chunk 警告，未阻断本阶段验收。

## 真实服务验收

按顺序轮换启动当前代码：

1. `local/desktop` 后端 + `npm run dev:local`
2. `saas/desktop` 后端 + `npm run dev:saas`
3. `saas/mobile` 后端 + `npm run dev:mobile`
4. 最终回到 `local/desktop` 后端 + `npm run dev:local`

每轮检查：

- 后端根路径：`http://127.0.0.1:8000/`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`
- 后端能力矩阵：`http://127.0.0.1:8000/api/capabilities`
- 前端根路径：`http://127.0.0.1:5173/`
- Vite `/api` 代理：`http://127.0.0.1:5173/api/capabilities`

最终保留服务：

- 前端：`http://127.0.0.1:5173/`
- 后端：`http://127.0.0.1:8000/`
- API Docs：`http://127.0.0.1:8000/docs`
- 当前 capabilities：`local/desktop`，`authRequired=false`

## 浏览器验收

使用 Chrome headless 检查真实 DOM 和截图：

| 壳 | 检查 |
|----|------|
| Local Desktop | DOM 包含“本机项目”“添加命令行智能体”，不包含 SaaS 主入口词汇。截图：`.agenthub-runtime/screenshots/final-local.png` |
| SaaS Web | DOM 包含“个人空间”“云端项目”“添加云端智能体”，不包含本机目录/命令行主入口词汇。截图：`.agenthub-runtime/screenshots/saas-web.png` |
| Mobile | DOM 包含“AgentHub Mobile”“会话”“通知”“审批”“产物”，不包含本机项目、命令行 Agent、完整工作区设置。截图：`.agenthub-runtime/screenshots/mobile-484.png` |

移动端截图时发现 Chrome headless 在当前 Windows 显示缩放下会把 `--window-size=390` 当物理像素处理，导致 390px 截图右侧裁切。已用 DevTools Protocol 验证真实 CSS 布局中 4 个底栏按钮均在 nav 内，并保留 `mobile-484.png` 作为不裁切的可视验收截图。

## AC 对照

| AC | 结论 |
|----|------|
| AC-P13-01 / 02 / 03 | 通过。LocalDesktopShell 独立启动，本机项目和本地 Artifact actions 可见，SaaS 入口不出现。 |
| AC-P13-04 / 05 / 06 / 07 | 通过。SaaS Web 显示个人空间/团队、cloud Project 和云端 actions，隐藏本机目录/executable/localhost 发布入口。 |
| AC-P13-08 / 09 / 10 | 通过。MobileShell 单列布局，会话/通知/审批/产物入口可见，不加载桌面三栏和本机特权能力。 |
| AC-P13-11 / 12 | 通过。`/api/capabilities` 驱动三端门禁；API client 不再默认注入 cloud dev header。 |
| AC-P13-13 / 14 / 15 | 通过。三端构建、Tauri skeleton smoke、Capacitor skeleton smoke 均通过。 |
| AC-P13-16 | 通过。P1 local、P2 SaaS cloud slice、Mobile approval/preview 入口均完成真实服务轮换验收。 |

## 剩余边界

- Tauri/Capacitor 当前是 packaging skeleton 和 smoke，不包含商店级打包、签名、自动更新。
- SaaS 认证仍为开发态 auth provider，生产登录/SSO 不属于 Phase 13。
- Chrome headless 截图受 Windows 显示缩放影响，后续可引入 Playwright 固定 viewport 与 device scale。

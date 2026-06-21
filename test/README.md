# 测试目录

本目录存放当前仍维护、可运行、可用于回归的测试。历史 Phase 脚本、运行残留和不可复用的临时验收脚本不再保留在主测试入口中。

## 目录结构

- `backend/api/`：后端 API 与集成测试。
- `backend/unit/`：后端单元测试。
- `backend/real/`：需要真实 CLI、真实服务或真实外部环境的手动/按需测试。
- `backend/fixtures/`：后端测试夹具资源。
- `backend/test_smoke.py`：后端冒烟测试。
- `frontend/`：前端组件、store、hook 与 API 客户端测试。

## 执行命令

```powershell
cd backend
python -m pytest -q
```

```powershell
cd frontend
npm test
npx tsc --noEmit
```

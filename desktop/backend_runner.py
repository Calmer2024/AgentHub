"""AgentHub 桌面版后端 runner。

该入口供 PyInstaller 打成 Tauri sidecar 使用。必须在导入 FastAPI app
之前写入本地桌面版环境变量，避免 packaged exe 使用临时解包目录作为数据目录。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def _default_data_dir() -> Path:
    configured = os.environ.get("AGENTHUB_DESKTOP_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AgentHub Local Desktop"
    return Path.home() / ".agenthub-local-desktop"


def _configure_environment() -> int:
    data_dir = _default_data_dir().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "workspaces").mkdir(parents=True, exist_ok=True)
    (data_dir / "deployments").mkdir(parents=True, exist_ok=True)

    port = int(os.environ.get("AGENTHUB_DESKTOP_PORT", "8188"))
    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{(data_dir / 'agenthub.db').as_posix()}")
    os.environ.setdefault("AGENTHUB_WORKSPACE_ROOT", str(data_dir / "workspaces"))
    os.environ.setdefault("AGENTHUB_DEPLOYMENT_ROOT", str(data_dir / "deployments"))
    os.environ.setdefault("AGENTHUB_EDITION", "local")
    os.environ.setdefault("AGENTHUB_SURFACE", "desktop")
    os.environ.setdefault("AGENTHUB_AUTH_REQUIRED", "false")
    os.environ.setdefault("AGENTHUB_DEV_AUTH_ENABLED", "true")
    os.environ.setdefault("AGENTHUB_API_BASE_URL", f"http://127.0.0.1:{port}")
    os.environ.setdefault(
        "CORS_ORIGINS",
        "["
        '"http://tauri.localhost",'
        '"https://tauri.localhost",'
        '"tauri://localhost",'
        '"http://127.0.0.1:5173",'
        '"http://localhost:5173"'
        "]",
    )
    return port


def main() -> int:
    port = _configure_environment()

    from app.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level=os.environ.get("AGENTHUB_DESKTOP_LOG_LEVEL", "warning"),
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""根 conftest —— 在所有 app 模块导入前设置测试环境。

pytest 从根到叶加载 conftest，此文件在 test/backend/api/conftest.py
（其中 import app.main → 触发 Settings() 实例化）之前执行。
"""

import os
import shutil
from pathlib import Path

_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
_repo_root = Path(__file__).resolve().parents[2]
_test_runtime_root = _repo_root / "test" / ".runtime" / _worker_id
_test_temp_root = _test_runtime_root / "tmp"
_test_db_path = str(_test_runtime_root / f"agenthub_test_{_worker_id}.db")
_test_workspace_root = _test_runtime_root / "workspaces"

_test_temp_root.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"
os.environ["AGENTHUB_WORKSPACE_ROOT"] = str(_test_workspace_root)
os.environ["TMP"] = str(_test_temp_root)
os.environ["TEMP"] = str(_test_temp_root)
# WAL 模式：允许并发读 + 单写，避免多连接锁冲突
os.environ["SQLALCHEMY_CONNECT_ARGS"] = '{"timeout": 30}'

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-dummy-key-12345678")


def pytest_configure(config):
    """测试启动前删除上一次可能残留的 DB 和 workspace。"""
    for path in [_test_db_path, _test_db_path + "-wal", _test_db_path + "-shm"]:
        try:
            os.unlink(path)
        except (FileNotFoundError, PermissionError):
            pass
    shutil.rmtree(_test_workspace_root, ignore_errors=True)


def pytest_sessionfinish(session, exitstatus):
    """测试全部完成后清理临时 DB 和 workspace。"""
    for path in [_test_db_path, _test_db_path + "-wal", _test_db_path + "-shm"]:
        try:
            os.unlink(path)
        except (FileNotFoundError, PermissionError):
            pass
    shutil.rmtree(_test_workspace_root, ignore_errors=True)

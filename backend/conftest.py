"""根 conftest —— 在所有 app 模块导入前设置测试环境。

pytest 从根到叶加载 conftest，此文件在 test_api/conftest.py
（其中 import app.main → 触发 Settings() 实例化）之前执行。
"""

import os
import shutil
import tempfile
from pathlib import Path

_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
_test_db_path = os.path.join(tempfile.gettempdir(), f"agenthub_test_{_worker_id}.db")
_test_workspace_root = Path(tempfile.gettempdir()) / f"agenthub_test_workspaces_{_worker_id}"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"
os.environ["AGENTHUB_WORKSPACE_ROOT"] = str(_test_workspace_root)
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

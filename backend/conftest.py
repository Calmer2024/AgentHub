"""根 conftest —— 在所有 app 模块导入前设置测试环境。

pytest 从根到叶加载 conftest，此文件在 test_api/conftest.py
（其中 import app.main → 触发 Settings() 实例化）之前执行。
"""

import os
import tempfile

_worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
_test_db_path = os.path.join(tempfile.gettempdir(), f"agenthub_test_{_worker_id}.db")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"
# WAL 模式：允许并发读 + 单写，避免多连接锁冲突
os.environ["SQLALCHEMY_CONNECT_ARGS"] = '{"timeout": 30}'

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy-key-12345678")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-dummy-key-12345678")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-12345678")
os.environ.setdefault("GEMINI_API_KEY", "AIza-test-dummy-key-12345-abcd")
os.environ.setdefault("MINIMAX_API_KEY", "test-dummy-minimax-key-1234567890")
os.environ.setdefault("GLM_API_KEY", "test-dummy-glm-key-1234567890")


def pytest_configure(config):
    """测试启动前删除上一次可能残留的 DB 文件。"""
    for path in [_test_db_path, _test_db_path + "-wal", _test_db_path + "-shm"]:
        try:
            os.unlink(path)
        except (FileNotFoundError, PermissionError):
            pass


def pytest_sessionfinish(session, exitstatus):
    """测试全部完成后清理临时 DB 文件。"""
    for path in [_test_db_path, _test_db_path + "-wal", _test_db_path + "-shm"]:
        try:
            os.unlink(path)
        except (FileNotFoundError, PermissionError):
            pass

"""冒烟测试 —— 验证所有模块可导入。每个 Phase 新增模块需在此添加。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_import_config():
    from app.config import settings
    assert hasattr(settings, "database_url")
    assert hasattr(settings, "deepseek_api_key")


def test_import_database():
    from app.database import Base, engine, get_db, AsyncSessionLocal
    assert Base is not None
    assert engine is not None


def test_import_models():
    from app.models import Session, Message
    assert hasattr(Session, "__tablename__")
    assert hasattr(Message, "__tablename__")


def test_import_cli_adapters():
    from app.agents import ClaudeCodeAdapter, CodexAdapter, OpenCodeAdapter
    assert ClaudeCodeAdapter is not None
    assert CodexAdapter is not None
    assert OpenCodeAdapter is not None


def test_import_system_models():
    from app.system_models import DeepSeekSystemAdapter, SystemModelCapability, SystemModelResponse
    assert DeepSeekSystemAdapter.DEFAULT_MODEL
    assert SystemModelCapability is not None
    assert SystemModelResponse is not None


def test_import_api_routes():
    from app.api import api_router
    assert api_router is not None


def test_import_main_app():
    from app.main import app
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)


def test_import_chat_router():
    from app.api.chat import router
    from fastapi import APIRouter
    assert isinstance(router, APIRouter)


def test_import_event_bus():
    from app.event_bus import EventBus, InMemoryEventBus, EventType
    assert EventBus is not None
    assert InMemoryEventBus is not None
    assert hasattr(EventType, "MESSAGE_COMPLETED")


def test_import_services():
    from app.services import MessageService, ChatService, SessionService
    from app.services.schemas import MessageCreate, MessageRead, SessionCreate, SessionRead
    from app.services.shared_context import SharedContext
    from app.services.token_event import TokenEvent
    from app.services.group_chat_stream import GroupChatStream
    from app.services.group_chat_finalizer import GroupChatFinalizer
    from app.services.orchestrator_summarizer import OrchestratorSummarizer
    assert MessageService is not None
    assert ChatService is not None
    assert SessionService is not None
    assert SharedContext is not None
    assert TokenEvent is not None
    assert GroupChatStream is not None
    assert GroupChatFinalizer is not None
    assert OrchestratorSummarizer is not None


def test_import_migration_runner():
    from migrations.migration_runner import run, ensure_history_table
    assert run is not None
    assert ensure_history_table is not None


def test_all_migration_files_exist():
    from migrations.migration_runner import MIGRATIONS_DIR
    files = [f for f in MIGRATIONS_DIR.iterdir() if f.suffix == ".sql"]
    assert len(files) >= 8, f"预期至少 8 个迁移文件，实际 {len(files)}"
    assert any(f.name == "008_fix_messages_fts_update_trigger.sql" for f in files)


def test_test_db_is_file_not_memory():
    """验证测试使用文件数据库而非内存数据库。"""
    from app.config import settings
    assert ":memory:" not in settings.database_url, \
        f"测试数据库应为文件模式，实际: {settings.database_url}"
    assert "agenthub_test_" in settings.database_url, \
        f"测试数据库路径应包含 test 标识，实际: {settings.database_url}"

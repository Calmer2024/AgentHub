"""冒烟测试 —— 验证所有模块可导入。每个 Phase 新增模块需在此添加。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_import_config():
    from app.config import settings
    assert hasattr(settings, "database_url")
    assert hasattr(settings, "anthropic_api_key")
    assert hasattr(settings, "deepseek_api_key")


def test_import_database():
    from app.database import Base, engine, get_db, AsyncSessionLocal
    assert Base is not None
    assert engine is not None


def test_import_models():
    from app.models import Session, Message
    assert hasattr(Session, "__tablename__")
    assert hasattr(Message, "__tablename__")


def test_import_agent_base():
    from app.agents.base import BaseAgentAdapter, AgentCapability, AgentResponse
    assert BaseAgentAdapter is not None


def test_import_claude_adapter():
    from app.agents import ClaudeAdapter
    from app.agents.base import BaseAgentAdapter
    assert issubclass(ClaudeAdapter, BaseAgentAdapter)


def test_import_deepseek_adapter():
    from app.agents.deepseek_adapter import DeepSeekAdapter
    from app.agents.base import BaseAgentAdapter
    assert issubclass(DeepSeekAdapter, BaseAgentAdapter)


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


def test_import_sessions_router():
    from app.api.sessions import router
    from fastapi import APIRouter
    assert isinstance(router, APIRouter)

import uuid
from unittest import mock
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app, lifespan
from app.database import get_db, AsyncSessionLocal
from app.agents.base import BaseAgentAdapter, AgentCapability, AgentResponse
from app.agents.registry import agent_registry
from app.models import AgentConfig


class MockAgent(BaseAgentAdapter):
    MODELS = ["mock-model"]
    DEFAULT_MODEL = "mock-model"

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(name="mock", supports_streaming=True)

    async def chat(self, messages, system_prompt, on_token=None, model=None, tools=None):
        return AgentResponse(content="Hello World!", finish_reason="stop")

    async def chat_stream(self, messages, system_prompt, model=None, tools=None):
        for token in ["Hello", ", ", "World", "!"]:
            yield token


@pytest.fixture(autouse=True)
def _mock_write_env():
    with mock.patch("app.api.settings._write_env"):
        yield


@pytest_asyncio.fixture(loop_scope="session")
async def _lifespan():
    """触发一次 FastAPI lifespan —— create_all + 迁移 + EventBus + 默认种子。"""
    async with lifespan(app):
        # 启用 WAL 模式以避免多连接写锁冲突
        from app.database import engine
        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.commit()
        yield
    from app.database import engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def _cleanup_db():
    """每个测试结束后删除所有用户数据，确保隔离。"""
    yield
    from app.database import engine
    from sqlalchemy import text
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        for t in ("session_members", "messages", "artifacts", "sessions", "agent_configs"):
            try:
                await conn.execute(text(f"DELETE FROM {t}"))
            except Exception:
                pass
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    # 重新种子默认 Agent（lifespan 只在 session 级别运行一次）
    from app.models import AgentConfig
    import uuid as _uuid
    async with AsyncSessionLocal() as s:
        from sqlalchemy import select
        r = await s.execute(select(AgentConfig).limit(1))
        if not r.scalars().first():
            s.add(AgentConfig(
                id=str(_uuid.uuid4()),
                name="默认助手",
                description="通用对话助手，基于 DeepSeek V4 Flash",
                system_prompt="你是一个有帮助的 AI 助手。请用简洁清晰的方式回答用户的问题。",
                provider="deepseek",
                model="deepseek-v4-flash",
            ))
            await s.commit()


@pytest_asyncio.fixture(loop_scope="function")
async def test_client(_lifespan, _cleanup_db):
    """主测试客户端 —— 文件 DB + MockAgent。"""
    mock_agent = MockAgent()
    original_adapters = dict(agent_registry._adapters)

    for provider in agent_registry._adapters:
        agent_registry._adapters[provider] = mock_agent

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        from app.database import engine

        async with engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)

            async def override_get_db():
                yield session

            app.dependency_overrides[get_db] = override_get_db

            yield client

            app.dependency_overrides.clear()
            await session.close()

    agent_registry._adapters = original_adapters


@pytest_asyncio.fixture(loop_scope="function")
async def db_session(test_client):
    """独立 DB session，用于 fixture 工厂 (test_agent, test_session)。"""
    from app.database import engine

    async with engine.connect() as conn:
        s = AsyncSession(bind=conn, expire_on_commit=False)
        yield s
        await s.close()


@pytest_asyncio.fixture
async def test_agent(db_session):
    agent = AgentConfig(
        id=str(uuid.uuid4()),
        name="测试 Agent",
        description="测试",
        system_prompt="你是一个测试助手。",
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    db_session.add(agent)
    await db_session.commit()
    return agent


@pytest_asyncio.fixture
async def test_session(test_client, db_session, test_agent):
    from app.models.session import Session

    sid = str(uuid.uuid4())
    sess = Session(id=sid, title="测试会话", agent_config_id=test_agent.id)
    db_session.add(sess)
    await db_session.commit()
    return sid

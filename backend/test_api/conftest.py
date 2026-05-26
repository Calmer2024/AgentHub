import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.database import Base, get_db
from app.agents.base import BaseAgentAdapter, AgentCapability, AgentResponse
from app.agents.registry import agent_registry

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class MockAgent(BaseAgentAdapter):
    """模拟 Agent，返回固定 token 流，不调用真实 API。"""

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="mock",
            supports_streaming=True,
        )

    async def chat(self, messages, system_prompt, on_token=None):
        return AgentResponse(content="Hello World!", finish_reason="stop")

    async def chat_stream(self, messages, system_prompt):
        for token in ["Hello", ", ", "World", "!"]:
            yield token


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture(loop_scope="session")
async def setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="function")
async def db_session(engine, setup_db):
    test_sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with test_sessionmaker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(loop_scope="function")
async def test_client(db_session):
    """测试客户端，DB 和 Agent 已 mock。"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    mock_agent = MockAgent()
    original_adapters = dict(agent_registry._adapters)
    original_is_available = agent_registry.is_available

    agent_registry._adapters = {"claude": mock_agent, "deepseek": mock_agent, "gemini": mock_agent}
    agent_registry.is_available = lambda name: name in agent_registry._adapters

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    agent_registry._adapters = original_adapters
    agent_registry.is_available = original_is_available
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_session(test_client, db_session):
    """创建一个可用于后续测试的 session。"""
    from app.models.session import Session
    import uuid

    sid = str(uuid.uuid4())
    sess = Session(id=sid, title="测试会话", agent_name="claude")
    db_session.add(sess)
    await db_session.commit()
    return sid

"""SessionService 单元测试 —— 覆盖 CRUD + 成员管理 + 异常流程。"""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models import AgentConfig, Session as DBSession
from app.services.session_service import (
    SessionService, SessionNotFoundError, AgentNotFoundError,
)
from app.services.schemas import SessionCreate, SessionUpdate

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    return create_async_engine(TEST_DB, echo=False)


@pytest.fixture(autouse=True)
async def setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db(engine):
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def test_agent(db: AsyncSession):
    agent = AgentConfig(
        id=str(uuid.uuid4()), name="测试 Agent", description="测试",
        system_prompt="你是一个测试助手。", provider="deepseek", model="deepseek-v4-flash",
    )
    db.add(agent)
    await db.commit()
    return agent


@pytest.fixture
def svc(db: AsyncSession):
    return SessionService(db)


class TestCreateSession:
    async def test_create_with_defaults(self, svc: SessionService, test_agent):
        data = SessionCreate()
        session = await svc.create_session(data)
        assert session.id
        assert session.title == "新对话"
        assert session.mode == "single"

    async def test_create_with_title(self, svc: SessionService, test_agent):
        data = SessionCreate(title="自定义标题")
        session = await svc.create_session(data)
        assert session.title == "自定义标题"

    async def test_create_group_session(self, svc: SessionService, test_agent):
        data = SessionCreate(
            title="项目讨论组",
            mode="group",
            agent_config_ids=[test_agent.id],
        )
        # 只有 1 个 agent → group 条件不满足，退化为 single
        session = await svc.create_session(data)
        assert session.mode == "single"


class TestListSessions:
    async def test_empty_list(self, svc: SessionService):
        sessions = await svc.list_sessions()
        assert len(sessions) == 0

    async def test_list_after_create(self, svc: SessionService, test_agent):
        await svc.create_session(SessionCreate(title="S1"))
        await svc.create_session(SessionCreate(title="S2"))
        sessions = await svc.list_sessions()
        assert len(sessions) == 2


class TestGetSession:
    async def test_get_existing(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="测试"))
        fetched = await svc.get_session(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_nonexistent(self, svc: SessionService):
        result = await svc.get_session("nonexistent-id")
        assert result is None


class TestUpdateSession:
    async def test_update_title(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="旧标题"))
        updated = await svc.update_session(created.id, SessionUpdate(title="新标题"))
        assert updated.title == "新标题"

    async def test_update_nonexistent_raises(self, svc: SessionService):
        with pytest.raises(SessionNotFoundError):
            await svc.update_session("nonexistent", SessionUpdate(title="x"))

    async def test_switch_to_invalid_agent_raises(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="测试"))
        with pytest.raises(AgentNotFoundError):
            await svc.update_session(created.id, SessionUpdate(agent_config_id="nonexistent"))


class TestDeleteSession:
    async def test_soft_delete(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="待删除"))
        ok = await svc.delete_session(created.id)
        assert ok is True
        # 软删除后仍在 DB 但 list 不返回
        sessions = await svc.list_sessions()
        assert len(sessions) == 0

    async def test_delete_nonexistent(self, svc: SessionService):
        ok = await svc.delete_session("nonexistent")
        assert ok is False


class TestMembers:
    async def test_empty_members(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="无成员"))
        members = await svc.get_members(created.id)
        assert len(members) == 0

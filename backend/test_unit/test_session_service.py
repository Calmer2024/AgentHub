"""SessionService 单元测试 —— 覆盖 CRUD + 成员管理 + 异常流程。"""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models import AgentConfig, Message as DBMessage, Session as DBSession
from app.services.session_service import (
    SessionService, SessionNotFoundError, AgentNotFoundError,
)
from app.services.schemas import ForwardMessagesRequest, SessionCreate, SessionUpdate

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
        system_prompt="你是一个测试助手。",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable="python",
        init_args="[]",
        env_vars="{}",
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

    async def test_pinned_sessions_sort_before_recent_items(self, svc: SessionService, test_agent):
        first = await svc.create_session(SessionCreate(title="较早置顶"))
        second = await svc.create_session(SessionCreate(title="较新普通"))
        await svc.update_session(first.id, SessionUpdate(is_pinned=True))

        sessions = await svc.list_sessions()

        assert sessions[0].id == first.id
        assert sessions[0].is_pinned is True
        assert sessions[1].id == second.id

    async def test_archived_sessions_hidden_by_default(self, svc: SessionService, test_agent):
        archived = await svc.create_session(SessionCreate(title="已归档"))
        visible = await svc.create_session(SessionCreate(title="仍显示"))
        await svc.update_session(archived.id, SessionUpdate(archived=True))

        sessions = await svc.list_sessions()
        all_sessions = await svc.list_sessions(include_archived=True)

        assert [session.id for session in sessions] == [visible.id]
        assert {session.id for session in all_sessions} == {archived.id, visible.id}
        assert next(session for session in all_sessions if session.id == archived.id).archived_at is not None


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

    async def test_update_pin_and_archive_flags(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="状态测试"))
        pinned = await svc.update_session(created.id, SessionUpdate(is_pinned=True))
        archived = await svc.update_session(created.id, SessionUpdate(archived=True))
        restored = await svc.update_session(created.id, SessionUpdate(is_pinned=False, archived=False))

        assert pinned.is_pinned is True
        assert archived.archived_at is not None
        assert restored.is_pinned is False
        assert restored.archived_at is None

    async def test_mute_and_mark_read(self, svc: SessionService, test_agent):
        created = await svc.create_session(SessionCreate(title="免打扰"))
        muted = await svc.update_session(created.id, SessionUpdate(is_muted=True))
        db_session = await svc.db.get(DBSession, created.id)
        assert db_session is not None
        SessionService.increment_unread(db_session, 3)
        await svc.db.commit()

        read = await svc.mark_read(created.id)

        assert muted.is_muted is True
        assert read.unread_count == 0
        assert read.last_read_at is not None

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


class TestForwardMessages:
    async def test_forward_messages_creates_real_user_messages(self, svc: SessionService, test_agent):
        source = await svc.create_session(SessionCreate(title="源对话"))
        target = await svc.create_session(SessionCreate(title="目标对话"))
        message = DBMessage(
            id=str(uuid.uuid4()),
            session_id=source.id,
            role="assistant",
            content="这里是需要转发的结论",
            content_type="text",
            agent_name="测试 Agent",
            source_type="agent",
            source_id=test_agent.id,
            source_name="测试 Agent",
        )
        svc.db.add(message)
        await svc.db.commit()

        result = await svc.forward_messages(ForwardMessagesRequest(
            messageIds=[message.id],
            targetSessionIds=[target.id],
        ))

        assert len(result.messages) == 1
        forwarded = result.messages[0]
        assert forwarded.session_id == target.id
        assert forwarded.role == "user"
        assert "转发自 测试 Agent" in forwarded.content
        assert forwarded.metadata is not None
        assert forwarded.metadata["forwarded"] is True
        assert forwarded.metadata["forwardSource"]["id"] == message.id

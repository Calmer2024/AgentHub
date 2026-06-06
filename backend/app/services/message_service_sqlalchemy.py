"""SQLAlchemy-backed message operations for Phase 4."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import Select, select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timezone import china_now, china_now_iso
from ..domain.context_manager import ContextManager, PromptAssemblyInput
from ..models import AgentConfig, Message as DBMessage, Session as DBSession
from .cli_agent_service import CliAgentService
from .message_service import MessageService
from .project_service import ProjectService, ProjectNotFoundError
from .schemas import MessageCreate, MessageRead

REGENERATE_TIMEOUT_SECONDS = 60
REPLY_REFERENCE_KEY = "replyReference"


class MessageNotFoundError(ValueError):
    """Raised when a target message does not exist."""


class InvalidMessageOperationError(ValueError):
    """Raised when a Phase 4 message operation is not allowed."""


class SqlAlchemyMessageService(MessageService):
    """Concrete MessageService implementation used by API and chat flows."""

    def __init__(self, db: AsyncSession, context_manager: ContextManager | None = None):
        self.db = db
        self.context_manager = context_manager or ContextManager()

    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
        before: str | None = None,
        include_internal: bool = False,
    ) -> list[MessageRead]:
        stmt: Select[tuple[DBMessage]] = (
            select(DBMessage)
            .where(DBMessage.session_id == session_id)
            .order_by(DBMessage.created_at.asc(), DBMessage.id.asc())
            .limit(limit)
        )
        if not include_internal:
            stmt = stmt.where(DBMessage.content_type != "orchestrator_task_result")
        if before:
            before_msg = await self.db.get(DBMessage, before)
            if before_msg and before_msg.created_at:
                stmt = stmt.where(DBMessage.created_at < before_msg.created_at)
        result = await self.db.execute(stmt)
        return [message_to_read(m) for m in result.scalars().all()]

    async def reply_to_message(
        self, input: MessageCreate, parent_message_id: str,
    ) -> MessageRead:
        parent = await self.db.get(DBMessage, parent_message_id)
        if not parent:
            raise MessageNotFoundError("parent message not found")
        if parent.session_id != input.session_id:
            raise InvalidMessageOperationError("parent message belongs to another session")

        metadata = build_reply_reference_metadata(parent, input.metadata)
        msg = DBMessage(
            id=str(uuid.uuid4()),
            session_id=input.session_id,
            role=input.role,
            content=input.content,
            content_type=input.content_type,
            source_type="user" if input.role == "user" else "assistant",
            source_name="用户" if input.role == "user" else None,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            parent_message_id=parent_message_id,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return message_to_read(msg)

    async def regenerate_message(self, message_id: str) -> AsyncIterator[str]:
        message = await self.db.get(DBMessage, message_id)
        if not message:
            yield self._sse({"done": True, "error": "message not found"})
            return
        if message.role != "assistant":
            yield self._sse({"done": True, "error": "only assistant messages can be regenerated"})
            return

        session = await self.db.get(DBSession, message.session_id)
        if not session:
            yield self._sse({"done": True, "error": "session not found"})
            return

        agent_config = await self._agent_for_message(message, session)
        if not agent_config:
            yield self._sse({"done": True, "error": "agent not found for message"})
            return

        history, pinned_ids = await self.history_for_session(message.session_id, before_message_id=message.id)
        if (agent_config.agent_type or "cli_wrapper") != "cli_wrapper":
            yield self._sse({
                "done": True,
                "error": f"Agent {agent_config.name} 不是 CLI Wrapper 类型，不能重新生成",
            })
            return

        async for item in self._regenerate_cli_message(message, session, agent_config, history, pinned_ids):
            yield item

    async def _regenerate_cli_message(
        self,
        message: DBMessage,
        session: DBSession,
        agent_config: AgentConfig,
        history: list[dict],
        pinned_ids: list[str],
    ) -> AsyncIterator[str]:
        try:
            workspace_path = await ProjectService(self.db).get_workspace_path_for_session(message.session_id)
        except ProjectNotFoundError:
            yield self._sse({"token": "", "done": True, "error": "当前会话未绑定项目，无法启动 CLI Agent", "messageId": message.id})
            return

        assembled = self.context_manager.assemble(PromptAssemblyInput(
            session_id=message.session_id,
            system_prompt=agent_config.system_prompt or "",
            messages=history,
            pinned_message_ids=pinned_ids,
            max_tokens=100_000,
        ))
        adapter_messages, system_prompt = _split_system_prompt(
            assembled.assembled_messages,
            agent_config.system_prompt or "",
        )

        original = message.content
        full = ""
        exit_code = None
        try:
            async with asyncio.timeout(REGENERATE_TIMEOUT_SECONDS):
                async for event in CliAgentService().stream(
                    agent=agent_config,
                    session_id=message.session_id,
                    workspace_path=workspace_path,
                    messages=adapter_messages,
                    system_prompt=system_prompt,
                ):
                    if event.type == "agent.output":
                        if event.chunk_type in {"text", "artifact_signal"}:
                            full += event.chunk
                            token = event.chunk if event.chunk_type == "text" else ""
                            yield self._sse({"token": token, "done": False, "messageId": message.id})
                    elif event.type == "agent.process.completed":
                        exit_code = event.exit_code
                    elif event.type in {"agent.process.timeout", "error"}:
                        yield self._sse({
                            "token": "",
                            "done": True,
                            "error": event.error or "CLI Agent 执行失败",
                            "messageId": message.id,
                        })
                        return
        except TimeoutError:
            yield self._sse({"token": "", "done": True, "error": "重新生成超时", "messageId": message.id})
            return
        except Exception as exc:
            yield self._sse({"token": "", "done": True, "error": f"{type(exc).__name__}: {exc}", "messageId": message.id})
            return

        if exit_code not in (0, None):
            yield self._sse({
                "token": "",
                "done": True,
                "error": f"CLI 进程异常退出（exit code: {exit_code}）",
                "messageId": message.id,
            })
            return

        metadata = _metadata_dict(message)
        versions = list(metadata.get("versions", []))
        versions.append({
            "content": original,
            "createdAt": china_now_iso(),
            "reason": "regenerate",
        })
        metadata["versions"] = versions[-5:]
        message.content = full
        message.metadata_json = json.dumps(metadata, ensure_ascii=False)
        session.updated_at = china_now()
        session.unread_count = max(0, int(getattr(session, "unread_count", 0) or 0) + 1)
        await self.db.commit()

        yield self._sse({
            "token": "",
            "done": True,
            "messageId": message.id,
            "agentName": agent_config.name,
        })

    async def pin_message(self, message_id: str) -> None:
        message = await self.db.get(DBMessage, message_id)
        if not message:
            raise MessageNotFoundError("message not found")
        message.is_pinned = "1"
        await self.db.commit()

    async def unpin_message(self, message_id: str) -> None:
        message = await self.db.get(DBMessage, message_id)
        if not message:
            raise MessageNotFoundError("message not found")
        message.is_pinned = "0"
        await self.db.commit()

    async def get_pinned_messages(self, session_id: str) -> list[MessageRead]:
        result = await self.db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session_id, DBMessage.is_pinned == "1")
            .order_by(DBMessage.created_at.asc(), DBMessage.id.asc())
        )
        return [message_to_read(m) for m in result.scalars().all()]

    async def search_messages(
        self, session_id: str, query: str, limit: int = 20,
    ) -> list[MessageRead]:
        q = query.strip()
        if not q:
            return []
        capped_limit = max(1, min(limit, 50))
        try:
            fts_results = await self._search_fts(session_id, q, capped_limit)
            if fts_results:
                return fts_results
        except (OperationalError, SQLAlchemyError):
            await self.db.rollback()
        return await self._search_like(session_id, q, capped_limit)

    async def history_for_session(
        self, session_id: str, before_message_id: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict], list[str]]:
        filters = [DBMessage.session_id == session_id]
        if before_message_id:
            before_msg = await self.db.get(DBMessage, before_message_id)
            if before_msg and before_msg.created_at:
                filters.append(DBMessage.created_at < before_msg.created_at)

        recent_result = await self.db.execute(
            select(DBMessage)
            .where(*filters)
            .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
            .limit(limit)
        )
        recent = list(recent_result.scalars().all())

        pinned_result = await self.db.execute(
            select(DBMessage)
            .where(*filters, DBMessage.is_pinned == "1")
            .order_by(DBMessage.created_at.asc(), DBMessage.id.asc())
        )
        pinned = list(pinned_result.scalars().all())

        by_id = {m.id: m for m in [*recent, *pinned]}
        messages = sorted(by_id.values(), key=lambda m: (m.created_at or datetime.min, m.id))

        parent_lookup = dict(by_id)
        for message in messages:
            if message.parent_message_id and message.parent_message_id not in parent_lookup:
                parent = await self.db.get(DBMessage, message.parent_message_id)
                if parent and parent.session_id == session_id:
                    parent_lookup[parent.id] = parent

        latest_message_id = messages[-1].id if messages else None
        history = []
        for message in messages:
            is_current_turn = message.id == latest_message_id
            if message.parent_message_id:
                parent = parent_lookup.get(message.parent_message_id)
                history.append(_reply_context_message(message, parent, is_current_turn))
            priority = "current_turn" if is_current_turn else None
            history.append(message_to_prompt_dict(message, context_priority=priority))
        pinned_ids = [m.id for m in pinned]
        return history, pinned_ids

    async def _search_fts(self, session_id: str, query: str, limit: int) -> list[MessageRead]:
        result = await self.db.execute(text("""
            SELECT
                m.id, m.session_id, m.role, m.content, m.content_type,
                m.agent_name, m.source_type, m.source_id, m.source_name,
                m.metadata_json, m.parent_message_id, m.is_pinned, m.created_at,
                snippet(messages_fts, 0, '<mark>', '</mark>', '...', 40) AS highlight
            FROM messages_fts
            JOIN messages m ON m.rowid = messages_fts.rowid
            WHERE messages_fts MATCH :q AND m.session_id = :sid
            ORDER BY rank
            LIMIT :limit
        """), {"q": query, "sid": session_id, "limit": limit})
        rows = result.mappings().all()
        return [row_to_read(row) for row in rows]

    async def _search_like(self, session_id: str, query: str, limit: int) -> list[MessageRead]:
        like = f"%{query}%"
        result = await self.db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session_id, DBMessage.content.like(like))
            .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
            .limit(limit)
        )
        return [
            message_to_read(m, highlight=_highlight_like(m.content, query))
            for m in result.scalars().all()
        ]

    async def _agent_for_message(
        self, message: DBMessage, session: DBSession,
    ) -> AgentConfig | None:
        if message.source_id:
            agent = await self.db.get(AgentConfig, message.source_id)
            if agent:
                return agent
        if session.agent_config_id:
            return await self.db.get(AgentConfig, session.agent_config_id)
        if message.agent_name:
            result = await self.db.execute(
                select(AgentConfig).where(AgentConfig.name == message.agent_name).limit(1)
            )
            return result.scalars().first()
        return None

    @staticmethod
    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def message_to_read(message: DBMessage, highlight: str | None = None) -> MessageRead:
    metadata = _metadata_dict(message)
    return MessageRead(
        id=message.id,
        sessionId=message.session_id,
        role=message.role,
        content=message.content,
        contentType=getattr(message, "content_type", "text") or "text",
        agentName=message.agent_name,
        sourceType=getattr(message, "source_type", None) or _source_type(message),
        sourceId=getattr(message, "source_id", None),
        sourceName=getattr(message, "source_name", None) or message.agent_name,
        parentMessageId=getattr(message, "parent_message_id", None),
        isPinned=_is_pinned(message),
        metadata=metadata or None,
        agentRole=_optional_metadata_str(metadata, "agentRole"),
        phase=_optional_metadata_int(metadata, "phase"),
        taskName=_optional_metadata_str(metadata, "taskName"),
        isCollaborating=_optional_metadata_bool(metadata, "isCollaborating"),
        createdAt=message.created_at,
        highlight=highlight,
    )


def message_to_prompt_dict(
    message: DBMessage, context_priority: str | None = None,
) -> dict:
    data = {
        "role": message.role,
        "content": message.content,
        "id": message.id,
        "source_name": getattr(message, "source_name", None) or message.agent_name,
        "created_at": message.created_at.isoformat() if message.created_at else "",
    }
    if context_priority:
        data["context_priority"] = context_priority
    return data


def row_to_read(row) -> MessageRead:
    metadata = _parse_metadata(row["metadata_json"])
    return MessageRead(
        id=row["id"],
        sessionId=row["session_id"],
        role=row["role"],
        content=row["content"],
        contentType=row["content_type"] or "text",
        agentName=row["agent_name"],
        sourceType=row["source_type"] or ("user" if row["role"] == "user" else "agent"),
        sourceId=row["source_id"],
        sourceName=row["source_name"] or row["agent_name"],
        parentMessageId=row["parent_message_id"],
        isPinned=str(row["is_pinned"] or "0") == "1",
        metadata=metadata or None,
        agentRole=_optional_metadata_str(metadata, "agentRole"),
        phase=_optional_metadata_int(metadata, "phase"),
        taskName=_optional_metadata_str(metadata, "taskName"),
        isCollaborating=_optional_metadata_bool(metadata, "isCollaborating"),
        createdAt=row["created_at"],
        highlight=row["highlight"],
    )


def _metadata_dict(message: DBMessage) -> dict:
    return _parse_metadata(getattr(message, "metadata_json", None))


def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_pinned(message: DBMessage) -> bool:
    return str(getattr(message, "is_pinned", "0")) == "1"


def _optional_metadata_str(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _optional_metadata_int(metadata: dict, key: str) -> int | None:
    value = metadata.get(key)
    return value if isinstance(value, int) else None


def _optional_metadata_bool(metadata: dict, key: str) -> bool:
    return bool(metadata.get(key))


def _source_type(message: DBMessage) -> str:
    if message.role == "user":
        return "user"
    return "agent" if message.agent_name else "assistant"


def build_reply_reference_metadata(
    parent: DBMessage, base_metadata: dict | None = None,
) -> dict:
    """创建引用时保存一份不可变快照。"""
    metadata = dict(base_metadata or {})
    metadata[REPLY_REFERENCE_KEY] = _reference_snapshot(parent)
    return metadata


def _reference_snapshot(message: DBMessage) -> dict:
    speaker = getattr(message, "source_name", None) or message.agent_name or (
        "用户" if message.role == "user" else "AI"
    )
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "agentName": message.agent_name,
        "sourceName": speaker,
        "createdAt": message.created_at.isoformat() if message.created_at else "",
    }


def _reply_context_message(
    message: DBMessage, parent: DBMessage | None, is_current_turn: bool = False,
) -> dict:
    snapshot = _metadata_dict(message).get(REPLY_REFERENCE_KEY)
    snapshot = snapshot if isinstance(snapshot, dict) else None
    if snapshot:
        ref_id = str(snapshot.get("id") or message.parent_message_id)
        speaker = str(snapshot.get("sourceName") or snapshot.get("agentName") or "未知")
        created = str(snapshot.get("createdAt") or "")
        ref_content = str(snapshot.get("content") or "")
    elif parent:
        ref_id = parent.id
        speaker = getattr(parent, "source_name", None) or parent.agent_name or (
            "用户" if parent.role == "user" else "AI"
        )
        created = parent.created_at.isoformat() if parent.created_at else ""
        ref_content = parent.content
    else:
        ref_id = str(message.parent_message_id)
        speaker = ""
        created = ""
        ref_content = ""

    if not ref_content:
        content = (
            "[Reply context]\n"
            f"用户当前消息引用了一条已删除或不可访问的历史消息。"
            f"\n引用消息 id: {ref_id}"
        )
    else:
        scope = "当前消息" if is_current_turn else "历史消息"
        content = (
            "[Reply context]\n"
            f"用户引用了以下历史消息（来自{scope}）。"
            "回答当前问题时，请把这段引用视为用户明确点选的上下文。\n"
            f"引用消息 id: {ref_id}\n"
            f"作者: {speaker}\n"
            f"时间: {created}\n"
            f"内容:\n{ref_content}"
        )
    return {
        "role": "user",
        "content": content,
        "id": f"reply-context-{message.id}",
        "reply_to": message.parent_message_id,
        "is_reply_context": True,
        "context_priority": "current_reference" if is_current_turn else "reply_history",
    }


def _highlight_like(content: str, query: str) -> str:
    lower = content.lower()
    needle = query.lower()
    idx = lower.find(needle)
    if idx < 0:
        return content[:120]
    start = max(0, idx - 40)
    end = min(len(content), idx + len(query) + 40)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{content[start:idx]}<mark>{content[idx:idx + len(query)]}</mark>{content[idx + len(query):end]}{suffix}"


def _split_system_prompt(messages: list[dict], fallback: str) -> tuple[list[dict], str]:
    if messages and messages[0].get("role") == "system":
        return messages[1:], str(messages[0].get("content") or fallback)
    return messages, fallback

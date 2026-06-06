"""Phase 5 architecture contract tests for Artifact domain/service boundaries."""

import uuid

import pytest

from app.domain.artifact_editor import ArtifactEditor
from app.event_bus import EventType, InMemoryEventBus
from app.models import Artifact, Message
from app.services import artifact_service as artifact_service_module
from app.services.artifact_service import ArtifactService, EDIT_ARTIFACT_TOOL
from app.system_models import SystemModelResponse


def test_artifact_editor_is_pure_and_parses_tool_arguments():
    editor = ArtifactEditor()
    payload = editor.parse_tool_call([{
        "function": {
            "name": "edit_artifact",
            "arguments": '{"selection":"old","edit_type":"replace","replacement":"new"}',
        },
    }])

    assert payload == {
        "selection": "old",
        "edit_type": "replace",
        "replacement": "new",
    }
    assert editor.apply_tool_payload("hello old", "old", payload) == "hello new"
    assert "+hello new" in editor.build_diff("hello old", "hello new", 1, 2).diff


@pytest.mark.asyncio
async def test_artifact_service_publishes_events(db_session, test_session):
    bus = InMemoryEventBus()
    await bus.start()
    received = []

    async def on_created(payload):
        received.append((EventType.ARTIFACT_CREATED, payload))

    async def on_updated(payload):
        received.append((EventType.ARTIFACT_UPDATED, payload))

    bus.subscribe(EventType.ARTIFACT_CREATED, on_created)
    bus.subscribe(EventType.ARTIFACT_UPDATED, on_updated)

    message = Message(
        id=str(uuid.uuid4()),
        session_id=test_session,
        role="assistant",
        content="artifact",
        source_type="agent",
    )
    artifact = Artifact(
        id=str(uuid.uuid4()),
        session_id=test_session,
        message_id=message.id,
        type="code_diff",
        title="a.py",
        content="print('v1')",
        status="ready",
        version=1,
    )
    db_session.add_all([message, artifact])
    await db_session.commit()

    await ArtifactService(db_session, event_bus=bus).apply_edit(
        artifact.id,
        selection="print('v1')",
        instruction="confirm",
        proposed_content="print('v2')",
        apply=True,
    )
    await bus._queue.join()
    await bus.stop()

    assert [event for event, _payload in received] == [
        EventType.ARTIFACT_CREATED,
        EventType.ARTIFACT_UPDATED,
    ]
    assert received[0][1]["parentArtifactId"] == artifact.id
    assert received[1][1]["previousArtifactId"] == artifact.id


@pytest.mark.asyncio
async def test_artifact_service_uses_system_llm_tool_call(monkeypatch, db_session, test_session):
    seen = {}

    class FakeSystemLLM:
        @property
        def capability(self):
            return type("Capability", (), {"supports_tool_call": True})()

        def is_configured(self):
            return True

        async def chat(self, *, messages, system_prompt, tools=None):
            seen["messages"] = messages
            seen["system_prompt"] = system_prompt
            seen["tools"] = tools
            return SystemModelResponse(
                content="",
                tool_calls=[{
                    "function": {
                        "name": "edit_artifact",
                        "arguments": (
                            '{"selection":"old","edit_type":"replace",'
                            '"replacement":"new"}'
                        ),
                    },
                }],
            )

    message = Message(id=str(uuid.uuid4()), session_id=test_session, role="assistant", content="")
    artifact = Artifact(
        id=str(uuid.uuid4()),
        session_id=test_session,
        message_id=message.id,
        type="code_diff",
        title="a.py",
        content="old",
        status="ready",
        version=1,
    )
    db_session.add_all([message, artifact])
    await db_session.commit()
    monkeypatch.setattr(artifact_service_module, "system_llm", FakeSystemLLM())

    preview = await ArtifactService(db_session).preview_edit(
        artifact.id,
        selection="old",
        instruction="replace it",
    )

    assert seen["tools"] == [EDIT_ARTIFACT_TOOL]
    assert preview.strategy == "system_tool_call"
    assert preview.proposed_content == "new"

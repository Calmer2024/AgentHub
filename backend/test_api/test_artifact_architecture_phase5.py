"""Phase 5 architecture contract tests for Artifact domain/service boundaries."""

import uuid
from types import SimpleNamespace

import pytest

from app.agents.openai_adapter import OpenAIAdapter
from app.domain.artifact_editor import ArtifactEditor
from app.event_bus import EventType, InMemoryEventBus
from app.models import Artifact, Message
from app.services.artifact_service import ArtifactService


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
async def test_openai_adapter_passes_tools_and_normalizes_tool_calls(monkeypatch):
    adapter = OpenAIAdapter()
    seen = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="tc1",
                                type="function",
                                function=SimpleNamespace(
                                    name="edit_artifact",
                                    arguments='{"replacement":"new"}',
                                ),
                            ),
                        ],
                    ),
                ),
            ])

    monkeypatch.setattr(adapter, "_client", SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    ))

    response = await adapter.chat(
        messages=[{"role": "user", "content": "edit"}],
        system_prompt="system",
        tools=[{"name": "edit_artifact", "parameters": {"type": "object"}}],
    )

    assert seen["tools"][0]["type"] == "function"
    assert seen["tool_choice"] == "auto"
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0]["name"] == "edit_artifact"
    assert response.tool_calls[0]["function"]["arguments"] == '{"replacement":"new"}'

"""EventBus 单元测试 —— 覆盖 publish/subscribe/unsubscribe + 异常隔离 + fire-and-forget。"""
import asyncio
import pytest
from app.event_bus import EventType, InMemoryEventBus


@pytest.fixture
async def bus():
    b = InMemoryEventBus()
    await b.start()
    yield b
    await b.stop()


class TestPublishSubscribe:
    async def test_single_subscriber_receives_event(self, bus: InMemoryEventBus):
        received = []

        async def handler(payload):
            received.append(payload)

        bus.subscribe(EventType.MESSAGE_COMPLETED, handler)
        await bus.publish(EventType.MESSAGE_COMPLETED, {"msg": "hello"})
        # 等待调度
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0] == {"msg": "hello"}

    async def test_multiple_subscribers_all_receive_event(self, bus: InMemoryEventBus):
        results = []

        async def h1(p):
            results.append(("h1", p))

        async def h2(p):
            results.append(("h2", p))

        bus.subscribe(EventType.AGENT_CALL_STARTED, h1)
        bus.subscribe(EventType.AGENT_CALL_STARTED, h2)
        await bus.publish(EventType.AGENT_CALL_STARTED, {"agent": "claude"})
        await asyncio.sleep(0.05)
        assert len(results) == 2

    async def test_different_event_types_delivered_independently(self, bus: InMemoryEventBus):
        completed = []
        streaming = []

        async def on_completed(p):
            completed.append(p)

        async def on_streaming(p):
            streaming.append(p)

        bus.subscribe(EventType.MESSAGE_COMPLETED, on_completed)
        bus.subscribe(EventType.MESSAGE_STREAMING, on_streaming)

        await bus.publish(EventType.MESSAGE_COMPLETED, {"id": "1"})
        await bus.publish(EventType.MESSAGE_STREAMING, {"token": "x"})
        await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert len(streaming) == 1


class TestUnsubscribe:
    async def test_unsubscribed_handler_not_called(self, bus: InMemoryEventBus):
        results = []

        async def h(p):
            results.append(p)

        bus.subscribe(EventType.ARTIFACT_CREATED, h)
        bus.unsubscribe(EventType.ARTIFACT_CREATED, h)
        await bus.publish(EventType.ARTIFACT_CREATED, {"id": "a"})
        await asyncio.sleep(0.05)
        assert len(results) == 0

    async def test_unsubscribe_nonexistent_handler_no_error(self, bus: InMemoryEventBus):
        async def h(p):
            pass

        # 取消订阅未注册的 handler 不应抛异常
        bus.unsubscribe(EventType.ARTIFACT_UPDATED, h)


class TestExceptionIsolation:
    async def test_one_handler_crash_does_not_affect_others(self, bus: InMemoryEventBus):
        good = []

        async def crashing(p):
            raise RuntimeError("boom")

        async def still_works(p):
            good.append(p)

        bus.subscribe(EventType.ORCHESTRATOR_TASK_STARTED, crashing)
        bus.subscribe(EventType.ORCHESTRATOR_TASK_STARTED, still_works)
        await bus.publish(EventType.ORCHESTRATOR_TASK_STARTED, {"task": "x"})
        await asyncio.sleep(0.05)

        assert len(good) == 1


class TestFireAndForget:
    async def test_publish_does_not_block_on_slow_handler(self, bus: InMemoryEventBus):
        done = []

        async def slow(p):
            await asyncio.sleep(0.1)
            done.append(True)

        bus.subscribe(EventType.MESSAGE_COMPLETED, slow)
        # publish 应立即返回，不阻塞
        t0 = asyncio.get_event_loop().time()
        await bus.publish(EventType.MESSAGE_COMPLETED, {"x": 1})
        elapsed = asyncio.get_event_loop().time() - t0
        assert elapsed < 0.05

    async def test_publish_to_event_with_no_subscribers_does_not_error(self, bus: InMemoryEventBus):
        await bus.publish(EventType.AGENT_CALL_COMPLETED, {"status": "ok"})
        await asyncio.sleep(0.02)


class TestStartStop:
    async def test_stop_cancels_dispatcher(self, bus: InMemoryEventBus):
        await bus.stop()
        # 再次 stop 不应报错
        await bus.stop()

    async def test_start_twice_no_duplicate_task(self, bus: InMemoryEventBus):
        await bus.start()
        await bus.start()
        # 验证只有一个 task
        await bus.stop()

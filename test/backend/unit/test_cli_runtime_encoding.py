import asyncio
from types import SimpleNamespace

import pytest

from app.agents.cli_runtime import CliProcessManager
from app.agents.cli_session_runtime import CliSessionProcessRuntime
from app.agents.cli_rpc_session_runtime import CliRpcSessionRuntime


class SplitReader:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, _size: int) -> bytes:
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


@pytest.mark.asyncio
async def test_cli_runtime_pump_preserves_split_utf8_characters():
    raw = "洗护这个临时店名，视觉风格".encode("utf-8")
    chunks = [raw[:5], raw[5:9], raw[9:14], raw[14:]]
    queue = asyncio.Queue()

    await CliProcessManager._pump(SplitReader(chunks), "stdout", queue)

    texts = []
    while True:
        stream, text = await queue.get()
        if text is None:
            break
        assert stream == "stdout"
        texts.append(text)
    result = "".join(texts)
    assert result == "洗护这个临时店名，视觉风格"
    assert "�" not in result


@pytest.mark.asyncio
async def test_persistent_runtime_pump_preserves_split_utf8_characters():
    raw = "移动端页面信息顺序".encode("utf-8")
    chunks = [raw[:1], raw[1:4], raw[4:8], raw[8:]]
    queue = asyncio.Queue()

    await CliSessionProcessRuntime._pump(SplitReader(chunks), "stdout", queue)

    texts = []
    while True:
        _stream, text = await queue.get()
        if text is None:
            break
        texts.append(text)
    result = "".join(texts)
    assert result == "移动端页面信息顺序"
    assert "�" not in result


@pytest.mark.asyncio
async def test_rpc_stderr_loop_preserves_split_utf8_characters():
    raw = "价格根据类型体型展示起价".encode("utf-8")
    handle = SimpleNamespace(
        process=SimpleNamespace(stderr=SplitReader([raw[:2], raw[2:7], raw[7:]])),
        stderr_queue=asyncio.Queue(),
    )

    await CliRpcSessionRuntime._stderr_loop(handle)

    texts = []
    while True:
        text = await handle.stderr_queue.get()
        if text is None:
            break
        texts.append(text)
    result = "".join(texts)
    assert result == "价格根据类型体型展示起价"
    assert "�" not in result

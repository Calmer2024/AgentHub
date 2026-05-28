"""StreamMerger —— 并发异步生成器的交错合并。

Infrastructure 层通用工具，不依赖任何业务逻辑。
"""

import asyncio
from typing import AsyncIterator, TypeVar

T = TypeVar("T")


class StreamMerger:
    """并发执行多个异步生成器，按 token/事件 到达顺序交错输出。"""

    @staticmethod
    async def merge(generators: list[AsyncIterator[T]]) -> AsyncIterator[T]:
        queue: asyncio.Queue[T | None] = asyncio.Queue()
        done_count = 0
        gens = list(generators)
        total = len(gens)

        async def run(gen):
            nonlocal done_count
            try:
                async for item in gen:
                    await queue.put(item)
            finally:
                done_count += 1
                if done_count >= total:
                    await queue.put(None)

        tasks = [asyncio.create_task(run(g)) for g in gens]

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            for t in tasks:
                t.cancel()

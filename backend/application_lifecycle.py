"""应用拥有的后台任务；任务不会跨应用生命周期泄漏。"""

import asyncio
import logging
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

logger = logging.getLogger("backend")


class BackgroundTasks:
    def __init__(self, factories: Mapping[str, Callable[[], Coroutine[Any, Any, Any]]]):
        self._factories = dict(factories)
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._tasks:
            return
        try:
            for name, factory in self._factories.items():
                self._tasks.append(asyncio.create_task(factory(), name=name))
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(
                    "后台任务 %s 退出异常: %s", task.get_name(), type(result).__name__
                )

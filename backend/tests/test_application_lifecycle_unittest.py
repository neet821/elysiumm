"""应用必须拥有后台任务，退出时不得留下清理或协调循环。"""

import asyncio
import os
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ApplicationLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_application_starts_each_loop_once_and_joins_on_exit(self):
        os.environ.setdefault("SECRET_KEY", "test-lifecycle-only")
        import main

        started, stopped, tasks = [], [], []

        async def worker(name):
            started.append(name)
            tasks.append(asyncio.current_task())
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(name)

        try:
            with (
                patch.object(main, "run_cleanup_task", lambda: worker("cleanup")),
                patch.object(main, "run_music_reconcile_task", lambda: worker("music")),
                patch.object(
                    main, "run_live_reconcile_task", lambda: worker("live")
                ),
            ):
                async with main.app.router.lifespan_context(main.app):
                    await asyncio.sleep(0)
                    self.assertCountEqual(started, ["cleanup", "music", "live"])
                self.assertCountEqual(stopped, started)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def manager(self, factories):
        self.assertIsNotNone(
            importlib.util.find_spec("application_lifecycle"),
            "应用尚未统一管理后台任务的启动和退出",
        )
        from application_lifecycle import BackgroundTasks

        return BackgroundTasks(factories)

    async def test_start_is_idempotent_and_stop_waits_for_every_worker(self):
        started = []
        stopped = []

        async def worker(name):
            started.append(name)
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                stopped.append(name)

        manager = self.manager(
            {name: lambda n=name: worker(n) for name in ("cleanup", "music", "live")}
        )
        await manager.start()
        await manager.start()
        await asyncio.sleep(0)
        self.assertCountEqual(started, ["cleanup", "music", "live"])
        await manager.stop()
        self.assertCountEqual(stopped, started)
        await manager.stop()
        self.assertEqual(len(stopped), 3)

    async def test_partial_start_failure_cancels_already_created_tasks(self):
        tasks_before = set(asyncio.all_tasks())

        async def worker():
            await asyncio.Event().wait()

        def broken():
            raise RuntimeError("cannot start")

        manager = self.manager({"cleanup": worker, "music": broken})
        with self.assertRaisesRegex(RuntimeError, "cannot start"):
            await manager.start()
        self.assertEqual(set(asyncio.all_tasks()), tasks_before)

    async def test_worker_failure_does_not_prevent_other_workers_cleanup(self):
        stopped = []

        async def broken():
            raise RuntimeError("worker failed")

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)

        manager = self.manager({"cleanup": worker, "music": broken})
        await manager.start()
        await asyncio.sleep(0)
        await manager.stop()
        self.assertEqual(stopped, [True])

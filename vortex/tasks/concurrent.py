from __future__ import annotations
from typing import Any, Optional

from threading import Thread
from multiprocessing import Queue

from vortex.tasks.base import Context, Task, TaskList


class TaskThread(Thread):
    def thread_func(self) -> None:
        try:
            self.task(self.ctx)
        except BaseException as e:
            self.queue.put(e)
        else:
            self.queue.put(None)

    def __init__(self, ctx: Context, task: Task, queue: Queue[Optional[BaseException]]) -> None:
        super().__init__(target=self.thread_func)
        self.ctx = ctx
        self.task = task
        self.queue = queue


class ConcurrentTaskList(TaskList):
    def run(self, ctx: Context, *args: Any, **kws: Any) -> None:
        assert len(args) == 0
        assert len(kws) == 0
        queue: Queue[Optional[BaseException]] = Queue()
        threads = [TaskThread(ctx, t, queue) for t in self.tasks]
        for th in threads:
            th.start()

        e: Optional[BaseException] = None
        count = 0
        try:
            while count < len(threads):
                e = queue.get()
                if e is not None:
                    ctx._running = False
                    break
                else:
                    count += 1
        except KeyboardInterrupt as ke:
            ctx._running = False
            e = ke

        for th in threads:
            th.join()
        if e is not None:
            raise e

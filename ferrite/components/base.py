from __future__ import annotations
from typing import Dict, List, Optional

from dataclasses import dataclass

from ferrite.remote.base import Device


@dataclass
class Context:
    device: Optional[Device] = None
    capture: bool = False


@dataclass
class Artifact:
    path: str
    cached: bool = False


class Task:

    def __init__(self) -> None:
        self._name: Optional[str] = None

    def name(self) -> str:
        return self._name or str(self)

    def run(self, ctx: Context) -> None:
        raise NotImplementedError()

    def dependencies(self) -> List[Task]:
        return []

    def run_with_dependencies(self, ctx: Context) -> None:
        deps = self.dependencies()
        assert isinstance(deps, list)

        for dep in deps:
            dep.run_with_dependencies(ctx)

        self.run(ctx)

    def artifacts(self) -> List[Artifact]:
        return []


class FinalTask(Task):

    def __init__(self) -> None:
        super().__init__()


class TaskList(Task):

    def __init__(self, tasks: List[Task]) -> None:
        super().__init__()
        self.tasks = tasks

    def run(self, ctx: Context) -> None:
        for task in self.tasks:
            task.run(ctx)

    def dependencies(self) -> List[Task]:
        return [dep for task in self.tasks for dep in task.dependencies()]

    def artifacts(self) -> List[Artifact]:
        return [art for task in self.tasks for art in task.artifacts()]


class TaskWrapper(Task):

    def __init__(self, inner: Optional[Task] = None, deps: List[Task] = []) -> None:
        super().__init__()
        self.inner = inner
        self.deps = deps

    def name(self) -> str:
        if self.inner is not None:
            return self.inner.name()
        else:
            return super().name()

    def run(self, ctx: Context) -> None:
        if self.inner is not None:
            self.inner.run(ctx)

    def dependencies(self) -> List[Task]:
        inner_deps = []
        if self.inner is not None:
            inner_deps = self.inner.dependencies()
        return inner_deps + self.deps

    def artifacts(self) -> List[Artifact]:
        if self.inner is not None:
            return self.inner.artifacts()
        else:
            return []


class Component:

    def tasks(self) -> Dict[str, Task]:
        raise NotImplementedError()

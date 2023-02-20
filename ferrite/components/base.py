from __future__ import annotations
from typing import Callable, TypeVar, Any, Dict, overload, Optional, ContextManager, Set, List

from pathlib import Path
from dataclasses import dataclass, field
from inspect import signature, Parameter

from ferrite.utils.log import LogLevel
from ferrite.remote.base import Device


@dataclass
class Context:
    target_path: Path
    device: Optional[Device] = None
    log_level: LogLevel = LogLevel.WARNING
    update: bool = False
    local: bool = False
    jobs: Optional[int] = None

    _stack: List[Task] = field(default_factory=list)
    _visited: Set[Task] = field(default_factory=set)
    _guard: Optional[Callable[[Task, Context], ContextManager[None]]] = None
    _no_deps: bool = False

    @property
    def capture(self) -> bool:
        return self.log_level > LogLevel.INFO


class Task:

    def name(self) -> str:
        raise NotImplementedError()

    def __call__(self, ctx: Context, *args: Any, **kws: Any) -> None:
        if ctx._no_deps:
            if len(ctx._stack) > 0 and self != ctx._stack[-1]:
                return
        else:
            if self in ctx._visited:
                return

        if len(ctx._stack) > 0 and self in ctx._stack and ctx._stack[-1] != self:
            raise RuntimeError(f"Task dependency cycle detected for {self}")

        assert ctx._guard is not None
        with ctx._guard(self, ctx):
            ctx._stack.append(self)
            try:
                self.run(ctx, *args, **kws)
            finally:
                ctx._stack.pop()

        ctx._visited.add(self)

    def run(self, ctx: Context, *args: Any, **kws: Any) -> None:
        raise NotImplementedError()


class Component:

    def tasks(self) -> Dict[str, Task]:
        return {k: v for k, v in {k: getattr(self, k) for k in dir(self)}.items() if isinstance(v, Task)}


T = TypeVar("T", bound=Component, contravariant=True)


@dataclass(eq=False, repr=False)
class FunctionTask(Task):
    func: Callable[[Context], None]

    def __post_init__(self) -> None:
        self.__name__ = self.func.__name__
        self.__qualname__ = self.func.__qualname__

    def name(self) -> str:
        return self.__qualname__

    def run(self, ctx: Context, *args: Any, **kws: Any) -> None:
        self.func(ctx, *args, **kws)

    def __hash__(self) -> int:
        return hash(self.func)

    def __repr__(self) -> str:
        return self.func.__repr__()


@dataclass(eq=False, repr=False)
class UnboundedTask:
    method: Callable[[T, Context], None]
    bounded: Optional[BoundedTask] = None

    def __post_init__(self) -> None:
        self.__name__ = self.method.__name__
        self.__qualname__ = self.method.__qualname__

    @overload
    def __get__(self, obj: Component, type: type | None = None) -> Task:
        ...

    @overload
    def __get__(self, obj: None, type: type | None = None) -> UnboundedTask:
        ...

    def __get__(self, obj: Component | None, type: type | None = None) -> Task | UnboundedTask:
        if obj is not None:
            if self.bounded is None:
                self.bounded = BoundedTask(obj, self)
            return self.bounded
        else:
            return self

    def __set__(self, obj: Any, value: Any) -> None:
        raise AttributeError()

    def name(self) -> str:
        return self.__qualname__

    def run(self, owner: T, ctx: Context, *args: Any, **kws: Any) -> None:
        self.method(owner, ctx, *args, **kws)

    def __hash__(self) -> int:
        return hash(self.method)

    def __repr__(self) -> str:
        return self.method.__repr__()


@dataclass(eq=False, repr=False)
class BoundedTask(Task):
    owner: Component
    inner: UnboundedTask

    @property
    def method(self) -> Callable[[Context], None]:
        method: Callable[[Context], None] = self.inner.method.__get__(self.owner)
        return method

    def __post_init__(self) -> None:
        self.__name__ = self.method.__name__
        self.__qualname__ = self.method.__qualname__

    def name(self) -> str:
        return self.__qualname__

    def run(self, ctx: Context, *args: Any, **kws: Any) -> None:
        self.inner.run(self.owner, ctx, *args, **kws)

    def __hash__(self) -> int:
        return hash(self.method)

    def __repr__(self) -> str:
        return self.method.__repr__()


@overload
def task(func: Callable[[Context], None]) -> Task:
    ...


@overload
def task(func: Callable[[T, Context], None]) -> UnboundedTask:
    ...


def task(func: Any) -> Any:
    params = list(signature(func).parameters.values())

    assert len(params) >= 1
    if params[0].name == "self":
        method = True
        params = params[1:]
    else:
        method = False
    assert len(params) >= 1
    assert params[0].default is Parameter.empty
    assert all([p.default is not Parameter.empty for p in params[1:]])

    if method:
        return UnboundedTask(func)
    else:
        return FunctionTask(func)


@task
def empty(ctx: Context) -> None:
    pass


class TaskList(Task):

    def __init__(self, *tasks: Task) -> None:
        self.tasks = tasks

    def name(self) -> str:
        return f"TaskList({[t.name() for t in self.tasks]})"

    def run(self, ctx: Context, *args: Any, **kws: Any) -> None:
        assert len(args) == 0
        assert len(kws) == 0
        for task in self.tasks:
            task(ctx)


class DictComponent(Component):

    def __init__(self, **tasks: Task) -> None:
        self._tasks = tasks

    def tasks(self) -> Dict[str, Task]:
        return self._tasks


class ComponentGroup(Component):

    def components(self) -> Dict[str, Component]:
        raise NotImplementedError()

    def tasks(self) -> Dict[str, Task]:
        tasks: Dict[str, Task] = {}
        for comp_name, comp in self.components().items():
            for task_name, task in comp.tasks().items():
                key = f"{comp_name}.{task_name}"
                assert key not in tasks
                tasks[key] = task
        return tasks

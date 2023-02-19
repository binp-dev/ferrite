from __future__ import annotations
from typing import Callable, TypeVar, Type, Tuple, Any, Dict, overload
from dataclasses import dataclass


class Context:
    pass


class Task:

    def __call__(self, ctx: Context) -> None:
        raise NotImplementedError()


class Component:
    pass


T = TypeVar("T", bound=Component, contravariant=True)


@dataclass
class FunctionTask(Task):
    func: Callable[[Context], None]

    def __call__(self, ctx: Context) -> None:
        self.func(ctx)


@dataclass
class UnboundedTask:
    method: Callable[[T, Context], None]

    @overload
    def __get__(self, obj: Component, type: type | None = None) -> Task:
        ...

    @overload
    def __get__(self, obj: None, type: type | None = None) -> UnboundedTask:
        ...

    def __get__(self, obj: Component | None, type: type | None = None) -> Task | UnboundedTask:
        if obj is not None:
            return BoundedTask(obj, self)
        else:
            return self

    def __set__(self, obj: Any, value: Any) -> None:
        raise AttributeError()

    def __call__(self, owner: T, ctx: Context) -> None:
        self.method(owner, ctx)


@dataclass
class BoundedTask(Task):
    owner: Component
    inner: UnboundedTask

    def __call__(self, ctx: Context) -> None:
        self.inner(self.owner, ctx)


class CompMeta(type):

    def __new__(cls, name: str, bases: Tuple[type, ...], dct: Dict[str, Any]) -> type:
        this = super().__new__(cls, name, bases, dct)

        return this


def task(func: Callable[[Context], None]) -> Task:
    return FunctionTask(func)


def comptask(method: Callable[[T, Context], None]) -> UnboundedTask:
    return UnboundedTask(method)


def component(class_: type) -> Type[Component]:
    return class_


@task
def empty(ctx: Context) -> None:
    pass


@dataclass
class Test(Component):
    x: int

    @comptask
    def task(self, ctx: Context) -> None:
        print(f"test task: {self.x}")


print(f"{Test.task}")

ctx = Context()
test = Test(123)

print(f"{test.task}")

test.task(ctx)


def take(ctx: Context, fn: Callable[[Context], None]) -> None:
    fn(ctx)


take(ctx, test.task)

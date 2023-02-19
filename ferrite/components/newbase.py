from __future__ import annotations
from typing import Callable, TypeVar, Type, Tuple, Any, Dict, overload
from types import FunctionType, MethodType
from dataclasses import dataclass
from inspect import signature


class Context:
    pass


class Task:

    def __call__(self, ctx: Context) -> None:
        raise NotImplementedError()


class Component:
    pass


T = TypeVar("T", bound=Component, contravariant=True)


@dataclass(eq=False, repr=False)
class FunctionTask(Task):
    func: Callable[[Context], None]

    def __post_init__(self) -> None:
        self.__name__ = self.func.__name__
        self.__qualname__ = self.func.__qualname__

    def __call__(self, ctx: Context) -> None:
        self.func(ctx)

    def __hash__(self) -> int:
        return hash(self.func)

    def __repr__(self) -> str:
        return self.func.__repr__()


@dataclass(eq=False, repr=False)
class UnboundedTask:
    method: Callable[[T, Context], None]

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
            return BoundedTask(obj, self)
        else:
            return self

    def __set__(self, obj: Any, value: Any) -> None:
        raise AttributeError()

    def __call__(self, owner: T, ctx: Context) -> None:
        self.method(owner, ctx)

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

    def __call__(self, ctx: Context) -> None:
        self.inner(self.owner, ctx)

    def __hash__(self) -> int:
        return hash(self.method)

    def __repr__(self) -> str:
        return self.method.__repr__()


class CompMeta(type):

    def __new__(cls, name: str, bases: Tuple[type, ...], dct: Dict[str, Any]) -> type:
        this = super().__new__(cls, name, bases, dct)

        return this


@overload
def task(func: Callable[[Context], None]) -> Task:
    ...


@overload
def task(func: Callable[[T, Context], None]) -> UnboundedTask:
    ...


def task(func: Any) -> Any:
    params = signature(func).parameters
    print(params)
    if len(params) == 1:
        return FunctionTask(func)
    elif len(params) == 2:
        return UnboundedTask(func)
    else:
        raise TypeError(f"{func} has wrong signature")


def component(class_: type) -> Type[Component]:
    return class_


ctx = Context()


@task
def empty(ctx: Context) -> None:
    pass


print(f"{empty = }")
print(f"{hash(empty) = }")
empty(ctx)


@dataclass
class Test(Component):
    x: int

    @task
    def task(self, ctx: Context) -> None:
        print(f"test task: {self.x}")


print(f"{Test.task = }")
print(f"{hash(Test.task) = }")

test = Test(123)

print(f"{test.task = }")
print(f"{hash(test.task) = }")
print(f"{hash(test.task) = }")

a = Test(321)
b = Test(456)
print(f"{hash(a.task) = }")
print(f"{hash(b.task) = }")
a = b
print(f"{hash(a.task) = }")

test.task(ctx)


def take(ctx: Context, fn: Callable[[Context], None]) -> None:
    fn(ctx)


take(ctx, test.task)

print({k: v for k, v in {k: getattr(test, k) for k in dir(test)}.items() if isinstance(v, Task)})

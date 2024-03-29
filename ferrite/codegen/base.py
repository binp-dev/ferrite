from __future__ import annotations
from typing import Any, List, Optional, Sequence, Set, Union

from dataclasses import dataclass
from enum import Enum
from random import Random

from numpy.typing import DTypeLike

from ferrite.codegen.utils import indent
from ferrite.codegen.macros import io_read_type, io_result_type, io_write_type, ok, stream_read, stream_write, try_unwrap


@dataclass
class Context:
    prefix: Optional[str] = None
    iter_depth: int = 0
    test_attempts: int = 1


# FIXME: Remove global context
CONTEXT = Context()


class Name:

    def __init__(self, *args: Union[str, List[str], Name, None]):
        self.words: List[str] = []
        for arg in args:
            if isinstance(arg, Name):
                self.words += arg.words
            elif isinstance(arg, list):
                self.words += arg
            elif isinstance(arg, str):
                self.words.append(arg)
            elif arg is None:
                pass
            else:
                raise RuntimeError(f"Unsupported argument {type(arg).__name__}")

    def camel(self) -> str:
        return "".join([s[0].upper() + s[1:].lower() for s in self.words])

    def snake(self) -> str:
        return "_".join([s.lower() for s in self.words])

    @staticmethod
    def from_snake(snake: str) -> Name:
        return Name(snake.split("_"))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Name):
            raise NotImplementedError()
        return self.words == other.words

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, Name):
            raise NotImplementedError()
        return not (self == other)

    def __repr__(self) -> str:
        return f"[" + ", ".join(self.words) + "]"


class Location(Enum):
    NONE = 0
    INCLUDES = 1
    DECLARATION = 2
    DEFINITION = 3
    TESTS = 4


class Source:

    def __init__(
        self,
        location: Location,
        items: Sequence[List[str]] = [],
        deps: List[Optional[Source]] = [],
    ):
        self.location = location
        self.items = ["\n".join(s) + "\n" for s in items]
        self.deps = [p for p in deps if p is not None]

    def collect(self, location: Location, used: Optional[Set[int]] = None) -> List[str]:
        if used is None:
            used = set()

        result = []

        for dep in self.deps:
            result.extend(dep.collect(location, used))

        if self.location == location:
            for item in self.items:
                item_hash = hash(item)
                if item_hash not in used:
                    result.append(item)
                    used.add(item_hash)

        return result

    def make_source(self, location: Location, separator: str = "\n") -> str:
        return separator.join(self.collect(location))


class Include(Source):

    def __init__(self, path: str):
        super().__init__(Location.INCLUDES, [[f"#include <{path}>"]])


def declare_variable(c_type: str, variable: str) -> str:
    return f"{c_type} {variable}"


class Type:

    def __init__(self, sized: bool, trivial: bool = False):
        if trivial:
            assert sized
        self.sized = sized
        self.trivial = trivial

    def name(self) -> Name:
        raise NotImplementedError(type(self).__name__)

    def _debug_name(self) -> str:
        try:
            return self.name().camel()
        except NotImplementedError:
            return type(self).__name__

    def _not_implemented(self) -> RuntimeError:
        return NotImplementedError(self._debug_name())

    def size(self) -> int:
        raise self._not_implemented()

    def min_size(self) -> int:
        return self.size()

    def is_empty(self) -> bool:
        return self.sized and self.size() == 0

    def deps(self) -> List[Type]:
        return []

    def load(self, data: bytes) -> Any:
        raise self._not_implemented()

    def store(self, value: Any) -> bytes:
        raise self._not_implemented()

    def default(self) -> Any:
        raise self._not_implemented()

    def random(self, rng: Random) -> Any:
        raise self._not_implemented()

    def is_instance(self, value: Any) -> bool:
        raise self._not_implemented()

    def __instancecheck__(self, value: Any) -> bool:
        return self.is_instance(value)

    def np_dtype(self) -> DTypeLike:
        raise self._not_implemented()

    def c_type(self) -> str:
        raise self._not_implemented()

    def cpp_type(self) -> str:
        return self.c_type()

    def pyi_type(self) -> str:
        raise self._not_implemented()

    def pyi_np_dtype(self) -> str:
        raise self._not_implemented()

    def c_source(self) -> Optional[Source]:
        return None

    def _cpp_load_func_decl(self, stream: str) -> str:
        return f"{io_result_type(self.cpp_type())} {Name(self.name(), 'load').snake()}({io_read_type()} &{stream})"

    def _cpp_store_func_decl(self, stream: str, value: str) -> str:
        return f"{io_result_type()} {Name(self.name(), 'store').snake()}({io_write_type()} &{stream}, const {self.cpp_type()} &{value})"

    def cpp_source(self) -> Optional[Source]:
        if not self.trivial:
            raise self._not_implemented()

        load_decl = self._cpp_load_func_decl("stream")
        store_decl = self._cpp_store_func_decl("stream", "value")
        return Source(
            Location.DEFINITION,
            [
                [
                    f"{load_decl} {{",
                    f"    {self.cpp_type()} value = {self.cpp_object(self.default())};",
                    *indent(try_unwrap(stream_read("stream", "&value", self.size()))),
                    f"    return {ok('value')};",
                    f"}}",
                ],
                [
                    f"{store_decl} {{",
                    *indent(try_unwrap(stream_write("stream", "&value", self.size()))),
                    f"    return {ok()};",
                    f"}}",
                ],
            ],
            deps=[Source(
                Location.DECLARATION,
                [
                    [f"{load_decl};"],
                    [f"{store_decl};"],
                ],
            )],
        )

    def pyi_source(self) -> Optional[Source]:
        return None

    def c_size(self, obj: str) -> str:
        return str(self.size())

    def cpp_size(self, obj: str) -> str:
        return self.c_size(obj)

    def _c_size_extent(self, obj: str) -> str:
        raise self._not_implemented()

    def _cpp_size_extent(self, obj: str) -> str:
        raise self._not_implemented()

    def _cpp_load_func(self, stream: str) -> str:
        return f"{Name(self.name(), 'load').snake()}({stream})"

    def _cpp_store_func(self, stream: str, value: str) -> str:
        return f"{Name(self.name(), 'store').snake()}({stream}, {value})"

    def cpp_load(self, stream: str) -> str:
        if not self.trivial:
            raise self._not_implemented()
        return self._cpp_load_func(stream)

    def cpp_store(self, stream: str, value: str) -> str:
        if not self.trivial:
            raise self._not_implemented()
        return self._cpp_store_func(stream, value)

    def cpp_object(self, value: Any) -> str:
        raise self._not_implemented()

    def c_test(self, obj: str, src: str) -> List[str]:
        return self.cpp_test(obj, src)

    def cpp_test(self, dst: str, src: str) -> List[str]:
        return [f"EXPECT_EQ({dst}, {src});"]

    def _cpp_static_check(self) -> Optional[str]:
        return f"static_assert(sizeof({self.c_type()}) == size_t({self.size() if self.sized else self.min_size()}));"

    def test_source(self) -> Optional[Source]:
        if self.trivial:
            return None

        rng = Random(0xdeadbeef)
        static_check = self._cpp_static_check()
        return Source(
            Location.TESTS,
            [[
                f"TEST({Name(CONTEXT.prefix, 'test').camel()}, {self.name().camel()}) {{",
                *indent([
                    *([
                        static_check,
                        f"",
                    ] if static_check is not None else []),
                    f"std::vector<{self.cpp_type()}> srcs = {{",
                    *["    " + self.cpp_object(self.random(rng)) + "," for _ in range(CONTEXT.test_attempts)],
                    f"}};",
                    f"",
                    f"core::VecDeque<uint8_t> stream;",
                    f"core::Vec<uint8_t> buffer;",
                    f"for (size_t k = 0; k < {CONTEXT.test_attempts}; ++k) {{",
                    *indent([
                        f"const {self.cpp_type()} src = srcs[k];",
                        f"",
                        f"{self.cpp_store('stream', 'src')}.unwrap();",
                        f"ASSERT_EQ(stream.size(), {self.cpp_size('src')});",
                        f"",
                        f"buffer.clear();",
                        f"ASSERT_EQ(stream.view().read_into_stream(buffer, std::nullopt), {ok('stream.size()')});",
                        f"auto *obj = reinterpret_cast<{self.c_type()} *>(buffer.data());",
                        f"ASSERT_EQ({self.c_size('(*obj)')}, {self.cpp_size('src')});",
                        *self.c_test('(*obj)', 'src'),
                        f"",
                        f"const auto dst = {self.cpp_load('stream')}.unwrap();",
                        f"ASSERT_EQ({self.cpp_size('dst')}, {self.cpp_size('src')});",
                        *self.cpp_test('dst', 'src'),
                    ]),
                    f"}}",
                ]),
                f"}}",
            ]],
            deps=[ty.test_source() for ty in self.deps()],
        )

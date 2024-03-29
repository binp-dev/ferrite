from __future__ import annotations
from typing import Any, List, Optional, Tuple, Union

from random import Random

from ferrite.codegen.base import CONTEXT, Include, Location, Name, Type, Source
from ferrite.codegen.macros import ErrorKind, err, io_error, io_read_type, io_result_type, io_write_type, ok, stream_read, stream_write, try_unwrap
from ferrite.codegen.primitive import Int, Pointer
from ferrite.codegen.utils import indent, list_join
from ferrite.codegen.structure import Field


class VariantValue:

    def __init__(self, type: Variant, id: int, variant: Any):
        self._type = type
        self._id = id
        self.variant = variant

    def store(self) -> bytes:
        return self._type.store(self)


class Variant(Type):

    def __init__(self, name: Union[Name, str], variants: List[Field], sized: bool | None = None):
        all_variants_sized = all([f.type.sized for f in variants])
        if sized is None:
            sized = all_variants_sized
        elif sized is True:
            assert all_variants_sized
        super().__init__(sized=sized)
        self._name = name
        self.variants = variants
        self._id_type = Int(8)
        assert len(self.variants) < (1 << self._id_type.bits)

        # Variant types for convenience
        for f in self.variants:
            setattr(self, f.name.camel(), f.type)

    def _variants_with_comma(self) -> List[Tuple[Field, str]]:
        if len(self.variants) > 0:
            return [(f, ",") for f in self.variants[:-1]] + [(self.variants[-1], "")]
        else:
            return []

    def name(self) -> Name:
        return Name(self._name)

    def min_size(self) -> int:
        min_sizes = [f.type.min_size() for f in self.variants]
        if self.sized:
            return max(min_sizes) + self._id_type.size()
        else:
            return min(min_sizes) + self._id_type.size()

    def size(self) -> int:
        return max([f.type.size() for f in self.variants]) + self._id_type.size()

    def load(self, data: bytes) -> VariantValue:
        if self.sized:
            assert len(data) == self.size()

        id = self._id_type.load(data[:self._id_type.size()])

        var_data = data[self._id_type.size():]
        var_type = self.variants[id].type
        if self.sized:
            var_data = var_data[:var_type.size()]
        variant = var_type.load(var_data)

        return self.value(id, variant)

    def store(self, value: VariantValue) -> bytes:
        data = b""
        data += self._id_type.store(value._id)
        data += self.variants[value._id].type.store(value.variant)

        if self.sized:
            assert self.size() >= len(data)
            data += b'\0' * (self.size() - len(data))

        return data

    def value(self, id: int, value: Any) -> VariantValue:
        assert self.variants[id].type.is_instance(value)
        return VariantValue(self, id, value)

    def __call__(self, variant: Any) -> Any:
        value = None
        for i, f in enumerate(self.variants):
            if f.type.is_instance(variant):
                assert value is None, f"{type(variant).__name__} is ambiguous. Use `value` method instead to provide variant index."
                value = self.value(i, variant)
        assert value is not None, f"{type(variant).__name__} is not an instance of any variant."
        return value

    def random(self, rng: Random) -> VariantValue:
        id = rng.randrange(0, len(self.variants))
        variant = self.variants[id].type.random(rng)
        return self.value(id, variant)

    def is_instance(self, value: VariantValue) -> bool:
        return value._type is self

    def deps(self) -> List[Type]:
        return [f.type for f in self.variants]

    def _c_size_func_name(self) -> str:
        return Name(CONTEXT.prefix, self.name(), "size").snake()

    def _c_enum_type(self) -> str:
        return Name(CONTEXT.prefix, self.name(), "type").camel()

    def _c_enum_value(self, index: int) -> str:
        return Name(CONTEXT.prefix, self.name(), self.variants[index].name).snake().upper()

    def _c_enum_declaration(self) -> List[str]:
        return [
            f"typedef enum {self._c_enum_type()} {{",
            *[f"    {self._c_enum_value(i)} = {i}," for i, f in enumerate(self.variants)],
            f"}} {self._c_enum_type()};",
        ]

    def _c_struct_declaration(self) -> List[str]:
        return [
            f"typedef struct __attribute__((packed, aligned(1))) {{",
            f"    {self._id_type.c_type()} type;",
            f"    union {{",
            *[f"        {f.type.c_type()} {f.name.snake()};" for f in self.variants if not f.type.is_empty()],
            f"    }};",
            f"}} {self.c_type()};",
        ]

    def _c_size_decl(self) -> str:
        return f"size_t {self._c_size_func_name()}({Pointer(self, const=True).c_type()} obj)"

    def _c_size_definition(self) -> List[str]:
        return [
            f"{self._c_size_decl()} {{",
            f"    size_t size = {self._id_type.size()};",
            f"    switch (({self._c_enum_type()})(obj->type)) {{",
            *list_join([[
                f"    case {self._c_enum_value(i)}:",
                f"        size += {f.type.c_size(f'(obj->{f.name.snake()})')};",
                f"        break;",
            ] for i, f in enumerate(self.variants)]),
            f"    default:",
            f"        abort(); // unreachable",
            f"    }}",
            f"    return size;",
            f"}}",
        ]

    def _cpp_enum_type(self) -> str:
        return "TypeId"

    def _cpp_enum_value(self, index: int) -> str:
        return self.variants[index].name.snake().upper()

    def _cpp_enum_declaration(self) -> List[str]:
        return [
            f"enum class {self._cpp_enum_type()} {{",
            *[f"    {self._cpp_enum_value(i)} = {i}," for i, f in enumerate(self.variants)],
            f"}};",
        ]

    def _cpp_size_method_decl(self) -> str:
        return f"[[nodiscard]] size_t packed_size() const;"

    def _cpp_load_method_decl(self) -> str:
        return f"static {io_result_type(self.cpp_type())} load({io_read_type()} &stream);"

    def _cpp_store_method_decl(self) -> str:
        return f"{io_result_type()} store({io_write_type()} &write) const;"

    def _cpp_size_method_impl(self) -> List[str]:
        return [
            f"size_t {self.cpp_type()}::packed_size() const {{",
            *([
                f"    size_t size = {self._id_type.size()};",
                f"    switch (static_cast<TypeId>(variant.index())) {{",
                *list_join([[
                    f"    case {self._cpp_enum_type()}::{self._cpp_enum_value(i)}:",
                    f"        size += {f.type.cpp_size(f'std::get<{i}>(variant)')};",
                    f"        break;",
                ] for i, f in enumerate(self.variants)]),
                f"    default:",
                f"        core_unreachable();",
                f"    }}",
                f"    return size;",
            ] if not self.sized else [
                f"    return {self.size()};",
            ]),
            f"}}",
        ]

    def _cpp_load_variant(self, ty: Type, stream: str) -> List[str]:
        lines = []
        if ty.is_empty():
            lines += [f"{ty.cpp_type()} tmp;"]
        else:
            lines += try_unwrap(ty.cpp_load(stream), lambda x: f"{ty.cpp_type()} tmp = {x};")

        if self.sized:
            size_diff = self.size() - self._id_type.size() - ty.size()
            assert size_diff >= 0
            if size_diff != 0:
                lines += [
                    f"uint8_t buf[{size_diff}] = {{0}}; // Padding",
                    *try_unwrap(stream_read("stream", "buf", size_diff, cast=False)),
                ]

        lines += [f"return {ok(f'{self.cpp_type()}{{std::move(tmp)}}')};"]
        return lines

    def _cpp_load_method_impl(self) -> List[str]:
        return [
            f"{io_result_type(self.cpp_type())} {self.cpp_type()}::load({io_read_type()} &stream) {{",
            *indent(try_unwrap(self._id_type.cpp_load("stream"), lambda x: f"auto raw_id = {x};")),
            f"    if (raw_id >= {len(self.variants)}) {{ return {err(io_error(ErrorKind.INVALID_DATA))}; }}",
            f"",
            f"    switch (static_cast<{self._cpp_enum_type()}>(raw_id)) {{",
            *indent(
                list_join([[
                    f"case {self._cpp_enum_type()}::{self._cpp_enum_value(i)}: {{",
                    *indent(self._cpp_load_variant(f.type, "stream")),
                    f"}}",
                ] for i, f in enumerate(self.variants)])
            ),
            f"    }}",
            f"    core_unreachable();",
            f"}}",
        ]

    def _cpp_store_variant(self, ty: Type, stream: str, src: str) -> List[str]:
        lines = []
        if not ty.is_empty():
            lines += try_unwrap(ty.cpp_store(stream, src))

        if self.sized:
            size_diff = self.size() - self._id_type.size() - ty.size()
            assert size_diff >= 0
            if size_diff != 0:
                lines += [
                    f"uint8_t buf[{size_diff}] = {{0}};",
                    *try_unwrap(stream_write("stream", "buf", size_diff, cast=False)),
                ]

        lines += [f"return {ok()};"]
        return lines

    def _cpp_store_method_impl(self) -> List[str]:
        return [
            f"{io_result_type()} {self.cpp_type()}::store({io_write_type()} &stream) const {{",
            f"    const auto raw_id = static_cast<{self._id_type.cpp_type()}>(variant.index());",
            *indent(try_unwrap(self._id_type.cpp_store("stream", "raw_id"))),
            f"",
            f"    switch (static_cast<{self._cpp_enum_type()}>(raw_id)) {{",
            *indent(
                list_join([[
                    f"case {self._cpp_enum_type()}::{self._cpp_enum_value(i)}: {{",
                    *indent(self._cpp_store_variant(f.type, "stream", f"std::get<{i}>(variant)")),
                    f"}}",
                ] for i, f in enumerate(self.variants)])
            ),
            f"    }}",
            f"    core_unreachable();",
            f"}}",
        ]

    def _cpp_declaration(self) -> Source:
        sections = [self._cpp_enum_declaration()]

        sections.append([
            f"std::variant<",
            *[f"    {option.type.cpp_type()}{c}" for option, c in self._variants_with_comma()],
            f"> variant;",
        ])

        sections.append([
            self._cpp_size_method_decl(),
            self._cpp_load_method_decl(),
            self._cpp_store_method_decl(),
        ])

        return Source(
            Location.DECLARATION,
            [[
                f"class {self.cpp_type()} final {{",
                f"public:",
                *list_join([indent(lines) for lines in sections], [""]),
                f"}};",
            ]],
            deps=[
                Include("variant"),
                *[ty.cpp_source() for ty in self.deps()],
            ],
        )

    def _cpp_definition(self) -> Source:
        items = []

        if not self.is_empty():
            items.extend([
                self._cpp_size_method_impl(),
                self._cpp_load_method_impl(),
                self._cpp_store_method_impl(),
            ])

        return Source(
            Location.DEFINITION,
            items,
            deps=[self._cpp_declaration()],
        )

    def _cpp_static_check(self) -> Optional[str]:
        if self.sized:
            return super()._cpp_static_check()
        else:
            return None

    def c_type(self) -> str:
        return Name(CONTEXT.prefix, self.name()).camel()

    def cpp_type(self) -> str:
        return self.name().camel()

    def c_source(self) -> Source:
        decl_source = Source(
            Location.DECLARATION,
            [
                self._c_enum_declaration(),
                self._c_struct_declaration(),
                *([[f"{self._c_size_decl()};"]] if not self.sized else []),
            ],
            deps=[
                self._id_type.c_source(),
                *[ty.c_source() for ty in self.deps()],
            ],
        )
        return Source(
            Location.DEFINITION,
            [self._c_size_definition()] if not self.sized else [],
            deps=[decl_source],
        )

    def cpp_source(self) -> Source:
        return self._cpp_definition()

    def c_size(self, obj: str) -> str:
        if self.sized:
            return str(self.size())
        else:
            return f"{self._c_size_func_name()}(&{obj})"

    def cpp_size(self, obj: str) -> str:
        return f"{obj}.packed_size()"

    def cpp_load(self, stream: str) -> str:
        return f"{self.cpp_type()}::load({stream})"

    def cpp_store(self, stream: str, src: str) -> str:
        return f"{src}.store({stream})"

    def cpp_object(self, value: VariantValue) -> str:
        assert self.is_instance(value)
        return "".join([
            f"{self.cpp_type()}{{",
            self.variants[value._id].type.cpp_object(value.variant),
            f"}}",
        ])

    def c_test(self, obj: str, src: str) -> List[str]:
        return [
            f"ASSERT_EQ(static_cast<size_t>({obj}.type), {src}.variant.index());",
            f"switch ({obj}.type) {{",
            *list_join([[
                f"case {self._c_enum_value(i)}:",
                *([*indent(f.type.c_test(f"{obj}.{f.name.snake()}", f"std::get<{i}>({src}.variant)"))]
                  if not f.type.is_empty() else []),
                f"    break;",
            ] for i, f in enumerate(self.variants)]),
            f"default:",
            f"    ASSERT_TRUE(false);",
            f"    break;",
            f"}}",
        ]

    def cpp_test(self, dst: str, src: str) -> List[str]:
        return [
            f"ASSERT_EQ({dst}.variant.index(), {src}.variant.index());",
            f"switch ({dst}.variant.index()) {{",
            *list_join([[
                f"case static_cast<size_t>({self._c_enum_value(i)}):",
                *([*indent(f.type.cpp_test(f"std::get<{i}>({dst}.variant)", f"std::get<{i}>({src}.variant)"))]
                  if not f.type.is_empty() else []),
                f"    break;",
            ] for i, f in enumerate(self.variants)]),
            f"default:",
            f"    ASSERT_TRUE(false);",
            f"    break;",
            f"}}",
        ]

    def pyi_type(self) -> str:
        return self.cpp_type()

    def pyi_source(self) -> Optional[Source]:
        return Source(
            Location.DECLARATION,
            [[
                f"@dataclass",
                f"class {self.pyi_type()}:",
                f"",
                *[f"    {f.name.camel()} = {f.type.pyi_type()}" for f in self.variants],
                f"",
                f"    Variant = {' | '.join([f.type.pyi_type() for f in self.variants])}",
                f"",
                f"    variant: Variant",
                f"",
                f"    @staticmethod",
                f"    def load(data: bytes) -> {self.pyi_type()}:",
                f"        ...",
                f"",
                f"    def store(self) -> bytes:",
                f"        ...",
            ]],
            deps=[
                Source(Location.INCLUDES, [["from dataclasses import dataclass"]]),
                *[ty.pyi_source() for ty in self.deps()],
            ],
        )

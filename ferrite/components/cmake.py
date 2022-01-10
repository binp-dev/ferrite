from __future__ import annotations
from typing import Dict, List, Optional

import os

from ferrite.utils.run import run
from ferrite.components.base import Component, Task, Context
from ferrite.components.toolchains import Toolchain


class CmakeTask(Task):

    def __init__(self, owner: Cmake):
        super().__init__()
        self.owner = owner


class CmakeBuildTask(CmakeTask):

    def run(self, ctx: Context) -> None:
        self.owner.configure(ctx)
        self.owner.build(ctx)

    def artifacts(self) -> List[str]:
        return [self.owner.build_dir]


class CmakeTestTask(CmakeTask):

    def run(self, ctx: Context) -> None:
        self.owner.test(ctx)

    def dependencies(self) -> List[Task]:
        return [self.owner.build_task]


class Cmake(Component):

    def __init__(
        self,
        src_dir: str,
        build_dir: str,
        toolchain: Toolchain,
        opt: List[str] = [],
        env: Optional[Dict[str, str]] = None,
    ):
        super().__init__()

        self.src_dir = src_dir
        self.build_dir = build_dir
        self.toolchain = toolchain
        self.opt = opt
        self.env = env

        self.build_task = CmakeBuildTask(self)
        self.test_task = CmakeTestTask(self)

    def create_build_dir(self) -> None:
        os.makedirs(self.build_dir, exist_ok=True)

    def configure(self, ctx: Context) -> None:
        self.create_build_dir()
        run(
            [
                "cmake",
                *self.opt,
                self.src_dir,
            ],
            cwd=self.build_dir,
            add_env=self.env,
            quiet=ctx.capture,
        )

    def build(self, ctx: Context, target: Optional[str] = None, verbose: bool = False) -> None:
        run(
            [
                "cmake",
                "--build",
                self.build_dir,
                *(["--target", target] if target else []),
                "--parallel",
                *(["--verbose"] if verbose else []),
            ],
            cwd=self.build_dir,
            quiet=ctx.capture,
        )

    def test(self, ctx: Context) -> None:
        run(["ctest", "--verbose"], cwd=self.build_dir, quiet=ctx.capture)

    def tasks(self) -> Dict[str, Task]:
        return {
            "build": self.build_task,
            "test": self.test_task,
        }
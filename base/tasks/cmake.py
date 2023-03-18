from __future__ import annotations
from typing import Dict, List, Optional

from pathlib import Path
from dataclasses import dataclass

from ferrite.utils.path import TargetPath
from ferrite.utils.run import run
from ferrite.components.base import task, Component, Context
from ferrite.components.compiler import Gcc


@dataclass
class Cmake(Component):

    src_dir: Path | TargetPath
    build_dir: TargetPath
    cc: Gcc
    build_target: Optional[str] = None

    def create_build_dir(self, ctx: Context) -> None:
        (ctx.target_path / self.build_dir).mkdir(exist_ok=True)

    def env(self, ctx: Context) -> Dict[str, str]:
        return {}

    def opt(self, ctx: Context) -> List[str]:
        return []

    def configure(self, ctx: Context) -> None:
        self.create_build_dir(ctx)
        run(
            [
                "cmake",
                *self.opt(ctx),
                self.src_dir if isinstance(self.src_dir, Path) else ctx.target_path / self.src_dir,
            ],
            cwd=(ctx.target_path / self.build_dir),
            add_env=self.env(ctx),
            quiet=ctx.capture,
        )

    @task
    def build(self, ctx: Context, verbose: bool = False) -> None:
        self.cc.install(ctx)
        self.configure(ctx)

        run(
            [
                "cmake",
                "--build",
                ctx.target_path / self.build_dir,
                *(["--target", self.build_target] if self.build_target is not None else []),
                "--parallel",
                *([str(ctx.jobs)] if ctx.jobs is not None else []),
                *(["--verbose"] if verbose else []),
            ],
            cwd=(ctx.target_path / self.build_dir),
            quiet=ctx.capture,
        )


@dataclass
class CmakeRunnable(Cmake):

    @task
    def run(self, ctx: Context) -> None:
        self.build(ctx)
        run(
            [f"./{self.build_target}"],
            cwd=(ctx.target_path / self.build_dir),
            quiet=ctx.capture,
        )

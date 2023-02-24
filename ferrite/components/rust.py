from __future__ import annotations
from typing import Dict, List, Optional

import os
import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from subprocess import Popen, CalledProcessError

from ferrite.utils.path import TargetPath
from ferrite.utils.run import run, capture
from ferrite.components.base import task, Component, Context
from ferrite.components.compiler import Compiler, Gcc, GccCross, GccHost, Target

import logging

logger = logging.getLogger(__name__)


class Rustc(Compiler):

    def __init__(self, postfix: str, target: Target, cc: Gcc, toolchain: Optional[str] = None):
        super().__init__(f"rustc_{postfix}", target)
        self.path = TargetPath("rustup")
        self.cc = cc
        self.toolchain = "stable" if toolchain is None else toolchain

    def env(self, ctx: Context) -> Dict[str, str]:
        return {
            **({"RUSTUP_HOME": str(ctx.target_path / self.path)} if ctx.local else {}),
            "RUSTUP_TOOLCHAIN": self.toolchain,
        }

    @task
    def install(self, ctx: Context) -> None:
        self.cc.install(ctx)

        cmds = [
            ["rustup", "set", "profile", "minimal"],
            ["rustup", "target", "add", str(self.target)],
            *([] if not ctx.update else [["rustup", "update", "--force-non-host", f"{self.toolchain}-{self.target}"]]),
        ]
        for cmd in cmds:
            run(cmd, add_env=self.env(ctx), quiet=ctx.capture)


class RustcHost(Rustc):

    _target_pattern: re.Pattern[str] = re.compile(r"^Default host:\s+(\S+)$", re.MULTILINE)

    def __init__(self, cc: GccHost, toolchain: Optional[str] = None):
        info = capture(["rustup", "show"])
        match = re.search(self._target_pattern, info)
        assert match is not None, f"Cannot detect rustup host rustc:\n{info}"
        target = Target.from_str(match[1])
        super().__init__("host", target, cc, toolchain=toolchain)


class RustcCross(Rustc):

    def __init__(self, postfix: str, target: Target, cc: GccCross, toolchain: Optional[str] = None):
        super().__init__(postfix, target, cc, toolchain=toolchain)

    def env(self, ctx: Context) -> Dict[str, str]:
        target_uu = str(self.target).upper().replace("-", "_")
        linker = ctx.target_path / self.cc.bin("gcc")
        return {
            **super().env(ctx),
            f"CARGO_TARGET_{target_uu}_LINKER": str(linker),
        }


@dataclass
class Cargo(Component):
    src_dir: Path | TargetPath
    build_dir: TargetPath
    rustc: Rustc
    features: List[str] = field(default_factory=list)
    default_features: bool = True
    release: bool = False

    def __post_init__(self) -> None:
        self.home_dir = Path.cwd() / ".cargo"

    def log_env(self, ctx: Context) -> Dict[str, str]:
        return {"RUST_LOG": ctx.log_level.name()}

    def env(self, ctx: Context) -> Dict[str, str]:
        return {
            **self.rustc.env(ctx),
            **({"CARGO_HOME": str(self.home_dir)} if ctx.local else {}),
            "CARGO_TARGET_DIR": str(ctx.target_path / self.build_dir),
        }

    @property
    def bin_dir(self) -> TargetPath:
        return self.build_dir / str(self.rustc.target) / ("release" if self.release else "debug")

    def src_path(self, ctx: Context) -> Path:
        if isinstance(self.src_dir, Path):
            return self.src_dir
        else:
            return ctx.target_path / self.src_dir

    @task
    def build(self, ctx: Context) -> None:
        self.rustc.install(ctx)

        cmds = [
            *([["cargo", "update"]] if ctx.update else []),
            [
                "cargo",
                "build",
                f"--target={self.rustc.target}",
                f"--features={','.join(self.features)}",
                *(["--no-default-features"] if not self.default_features else []),
                *(["--release"] if self.release else []),
            ],
        ]
        for cmd in cmds:
            run(cmd, cwd=self.src_path(ctx), add_env=self.env(ctx), quiet=ctx.capture)

    @task
    def test(self, ctx: Context) -> None:
        self.rustc.install(ctx)

        run(
            [
                "cargo",
                "test",
                f"--features={','.join(self.features)}",
                *(["--no-default-features"] if not self.default_features else []),
                #"--",
                #"--nocapture",
            ],
            cwd=self.src_path(ctx),
            add_env=self.env(ctx),
            quiet=ctx.capture,
        )

    @task
    def run(self, ctx: Context, bin: Optional[str] = None) -> None:
        self.rustc.install(ctx)

        cmd = [
            "cargo",
            "run",
            *([bin] if bin is not None else []),
            f"--features={','.join(self.features)}",
            *(["--no-default-features"] if not self.default_features else []),
        ]
        env = {**dict(os.environ), **self.env(ctx)}
        proc: Optional[Popen[str]] = Popen(cmd, cwd=self.src_path(ctx), env=env, text=True)
        logger.debug(f"Program started: {cmd}")

        assert proc is not None
        while ctx._running:
            time.sleep(0.1)
            ret = proc.poll()
            if ret is not None:
                proc = None
                if ret != 0:
                    raise CalledProcessError(ret, cmd)
                break

        if proc is not None:
            logger.debug("Terminating program ...")
            proc.terminate()
            logger.debug(f"Program terminated")

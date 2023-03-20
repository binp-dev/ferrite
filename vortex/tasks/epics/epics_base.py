from __future__ import annotations
from typing import List, TypeVar

import shutil
from pathlib import Path, PurePosixPath

from vortex.utils.path import TargetPath
from vortex.utils.files import substitute, allow_patterns
from vortex.tasks.base import task, Context
from vortex.tasks.git import RepoList, RepoSource
from vortex.tasks.compiler import Gcc, GccHost, GccCross
from vortex.tasks.epics.base import EpicsProject

import logging

logger = logging.getLogger(__name__)


class AbstractEpicsBase(EpicsProject):
    def __init__(self, src_dir: Path | TargetPath, target_dir: TargetPath, cc: Gcc, blacklist: List[str] = []) -> None:
        super().__init__(
            src_dir,
            target_dir,
            cc,
            deploy_path=PurePosixPath("/opt/epics_base"),
            blacklist=[
                "*.a",
                "include/*",
                *blacklist,
            ],
        )

    def _configure_common(self, ctx: Context) -> None:
        defs = [
            # ("USR_CFLAGS", ""),
            # ("USR_CPPFLAGS", ""),
            ("USR_CXXFLAGS", "-std=c++20"),
            ("BIN_PERMISSIONS", "755"),
            ("LIB_PERMISSIONS", "644"),
            ("SHRLIB_PERMISSIONS", "755"),
            ("INSTALL_PERMISSIONS", "644"),
        ]
        rules = [(f"^(\\s*{k}\\s*=).*$", f"\\1 {v}") for k, v in defs]
        logger.info(rules)
        substitute(
            rules,
            ctx.target_path / self.build_dir / "configure/CONFIG_COMMON",
        )

    def _configure_toolchain(self, ctx: Context) -> None:
        raise NotImplementedError()

    def _configure_install(self, ctx: Context) -> None:
        substitute(
            [
                ("^\\s*#*(\\s*INSTALL_LOCATION\\s*=).*$", f"\\1 {ctx.target_path / self.install_dir}"),
            ],
            ctx.target_path / self.build_dir / "configure/CONFIG_SITE",
        )

    def _configure(self, ctx: Context) -> None:
        self._configure_common(ctx)
        self._configure_toolchain(ctx)
        # self._configure_install(ctx) # Install is broken

    @task
    def build(self, ctx: Context) -> None:
        super().build(ctx, clean=False)

    # Workaround for broken EPICS install
    def _install(self, ctx: Context) -> None:
        # Copy all required dirs manually
        paths = [
            "bin",
            "cfg",
            # "configure",
            "db",
            "dbd",
            # "html",
            "include",
            "lib",
            # "templates",
        ]
        for path in paths:
            shutil.rmtree(
                ctx.target_path / self.install_dir / path,
                ignore_errors=True,
            )
            shutil.copytree(
                ctx.target_path / self.build_dir / path,
                ctx.target_path / self.install_dir / path,
                symlinks=True,
                ignore=shutil.ignore_patterns("O.*"),
            )

    @task
    def deploy(self, ctx: Context) -> None:
        self.build(ctx)
        super().deploy(ctx)


class EpicsBaseHost(AbstractEpicsBase):
    def __init__(self, cc: GccHost):
        self.version = "7.0.6.1"
        name = f"epics_base_{self.version}"

        super().__init__(TargetPath(name) / "src", TargetPath(name), cc)

        self.name = name

        assert isinstance(self.src_dir, TargetPath)
        self.repo = RepoList(
            self.src_dir,
            [
                RepoSource("https://gitlab.inp.nsk.su/epics/epics-base.git", f"binp-R{self.version}"),
                RepoSource("https://github.com/epics-base/epics-base.git", f"R{self.version}"),
            ],
        )

    def _configure_toolchain(self, ctx: Context) -> None:
        substitute(
            [("^(\\s*CROSS_COMPILER_TARGET_ARCHS\\s*=).*$", "\\1")],
            ctx.target_path / self.build_dir / "configure/CONFIG_SITE",
        )

    @task
    def build(self, ctx: Context) -> None:
        self.repo.clone(ctx)
        super().build(ctx)


class EpicsBaseCross(AbstractEpicsBase):
    def __init__(self, cc: GccCross, host_base: EpicsBaseHost):
        super().__init__(
            host_base.build_dir,
            TargetPath(host_base.name),
            cc,
            blacklist=[f"*/{host_base.arch}/*"],
        )
        self.host_base = host_base

    def _configure_toolchain(self, ctx: Context) -> None:
        cc = self.cc

        host_arch = self.host_base.arch
        cross_arch = self.arch
        assert cross_arch != host_arch

        if cross_arch == "linux-arm" and host_arch.endswith("-x86_64"):
            host_arch = host_arch[:-3]  # Trim '_64'

        substitute(
            [("^(\\s*CROSS_COMPILER_TARGET_ARCHS\\s*=).*$", f"\\1 {cross_arch}")],
            ctx.target_path / self.build_dir / "configure/CONFIG_SITE",
        )
        substitute(
            [
                ("^(\\s*GNU_TARGET\\s*=).*$", f"\\1 {str(cc.target)}"),
                ("^(\\s*GNU_DIR\\s*=).*$", f"\\1 {ctx.target_path / cc.path}"),
            ],
            ctx.target_path / self.build_dir / f"configure/os/CONFIG_SITE.{host_arch}.{cross_arch}",
        )

    def _dep_paths(self, ctx: Context) -> List[Path]:
        return [
            *super()._dep_paths(ctx),
            ctx.target_path / self.host_base.build_dir,
        ]

    @task
    def build(self, ctx: Context) -> None:
        self.host_base.build(ctx)
        super().build(ctx)

    def _install(self, ctx: Context) -> None:
        super()._install(ctx)

        host_arch = self.host_base.arch
        cross_arch = self.arch
        assert cross_arch != host_arch

        shutil.copytree(
            ctx.target_path / self.build_dir / "bin" / host_arch,
            ctx.target_path / self.install_dir / "bin" / cross_arch,
            dirs_exist_ok=True,
            symlinks=True,
            ignore=allow_patterns("*.pl", "*.py"),
        )

from __future__ import annotations
from typing import List

import shutil
from pathlib import Path, PurePosixPath

from vortex.utils.path import TargetPath
from vortex.utils.run import capture, run
from vortex.tasks.base import task, Component, Context
from vortex.tasks.compiler import Target, Gcc
from vortex.tasks.utils import TreeModInfo

import logging

logger = logging.getLogger(__name__)


def epics_host_arch(epics_base_dir: Path) -> str:
    return capture(["perl", epics_base_dir / "src" / "tools" / "EpicsHostArch.pl"])


def epics_arch_by_target(target: Target) -> str:
    if target.api == "linux":
        if target.isa == "x86_64":
            return "linux-x86_64"
        elif target.isa == "arm":
            return "linux-arm"
        elif target.isa == "aarch64":
            return "linux-aarch64"
    # TODO: Add some other archs
    raise Exception(f"Unknown target for EPICS: {str(target)}")


class EpicsProject(Component):
    def __init__(
        self,
        src_dir: Path | TargetPath,
        target_dir: TargetPath,
        cc: Gcc,
        deploy_path: PurePosixPath,
        blacklist: List[str] = [],
    ) -> None:
        super().__init__()
        target_name = cc.name
        self.src_dir = src_dir
        self.build_dir = target_dir / target_name / "build"
        self.install_dir = target_dir / target_name / "install"
        self.cc = cc
        self.deploy_path = deploy_path
        self.blacklist = blacklist

    @property
    def arch(self) -> str:
        return epics_arch_by_target(self.cc.target)

    def _prepare_source(self, ctx: Context) -> None:
        pass

    def _configure(self, ctx: Context) -> None:
        raise NotImplementedError()

    def _dep_paths(self, ctx: Context) -> List[Path]:
        "Dependent paths."
        return [ctx.target_path / self.src_dir]

    @task
    def build(self, ctx: Context, clean: bool = False) -> None:
        self.cc.install(ctx)

        build_path = ctx.target_path / self.build_dir

        info = TreeModInfo.load(build_path)
        if info is None or not info.newer_than(*self._dep_paths(ctx)):
            clean = True
        else:
            logger.info(f"'{build_path}' is already built")
            return

        if clean:
            shutil.rmtree(build_path, ignore_errors=True)

        self._prepare_source(ctx)

        shutil.copytree(
            ctx.target_path / self.src_dir,
            build_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git"),
        )

        logger.info(f"Configure {build_path}")
        self._configure(ctx)

        logger.info(f"Build {build_path}")
        run(
            ["make", "--jobs", *([str(ctx.jobs)] if ctx.jobs is not None else [])],
            cwd=build_path,
            quiet=ctx.capture,
        )

        TreeModInfo(build_path).store()

    def _install(self, ctx: Context) -> None:
        raise NotImplementedError()

    @task
    def install(self, ctx: Context) -> None:
        self.build(ctx)

        build_path = ctx.target_path / self.build_dir
        install_path = ctx.target_path / self.install_dir

        info = TreeModInfo.load(install_path)
        if info is not None and info.newer_than(build_path):
            logger.info(f"'{install_path}' is already installed")
            return

        logger.info(f"Install from {build_path} to {install_path}")
        shutil.rmtree(install_path, ignore_errors=True)
        install_path.mkdir()
        self._install(ctx)

        TreeModInfo(install_path).store()

    def _pre_deploy(self, ctx: Context) -> None:
        pass

    def _post_deploy(self, ctx: Context) -> None:
        pass

    @task
    def deploy(self, ctx: Context) -> None:
        self.install(ctx)

        install_path = ctx.target_path / self.install_dir
        assert ctx.device is not None
        self._pre_deploy(ctx)
        logger.info(f"Deploy {install_path} to {ctx.device.name()}:{self.deploy_path}")
        ctx.device.store(install_path, self.deploy_path, recursive=True, exclude=self.blacklist)
        self._post_deploy(ctx)

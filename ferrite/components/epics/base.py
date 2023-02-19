from __future__ import annotations
from typing import Dict, Any, List, ClassVar

import os
import shutil
from pathlib import Path, PurePosixPath
from dataclasses import dataclass, field
import json

from dataclass_type_validator import dataclass_validate, TypeValidationError

from ferrite.utils.path import TargetPath
from ferrite.utils.run import capture, run
from ferrite.components.base import task, Component, Context, Task
from ferrite.components.compiler import Target, Gcc

import logging

logger = logging.getLogger(__name__)


def epics_host_arch(epics_base_dir: Path) -> str:
    return capture([
        "perl",
        epics_base_dir / "src" / "tools" / "EpicsHostArch.pl",
    ])


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


# Milliseconds from the start of the epoch
def _tree_mod_time(path: Path) -> int:
    if path.is_dir():
        max_time = 0.0
        for dirpath, dirnames, filenames in os.walk(path):
            max_time = max([
                max_time,
                os.path.getmtime(dirpath),
                *[os.path.getmtime(os.path.join(dirpath, fn)) for fn in filenames],
            ])
    else:
        max_time = os.path.getmtime(path)
    return int(1000 * max_time)


@dataclass_validate
@dataclass
class _BuildInfo:
    build_dir: str
    dep_mod_times: Dict[str, int]

    FILE_NAME: ClassVar[str] = "build_info.json"

    @staticmethod
    def from_paths(base_dir: Path, dep_paths: List[Path]) -> _BuildInfo:
        return _BuildInfo(
            build_dir=str(base_dir),
            dep_mod_times={str(path): _tree_mod_time(path) for path in dep_paths},
        )

    @staticmethod
    def load(base_dir: Path) -> _BuildInfo:
        path = base_dir / _BuildInfo.FILE_NAME
        with open(path, "r") as f:
            return _BuildInfo(**json.load(f))

    def store(self, base_dir: Path) -> None:
        path = base_dir / _BuildInfo.FILE_NAME
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2, sort_keys=True)

    def has_changed_since(self, other: _BuildInfo) -> bool:
        if self.build_dir != other.build_dir:
            return True
        for path, time in self.dep_mod_times.items():
            try:
                if time > other.dep_mod_times[path]:
                    return True
            except KeyError:
                return True
        return False


class EpicsProject(Component):

    def __init__(
        self,
        src_dir: Path | TargetPath,
        target_dir: TargetPath,
        cc: Gcc,
    ) -> None:
        super().__init__()
        target_name = cc.name
        self.src_dir = src_dir
        self.build_dir = target_dir / target_name / "build"
        self.install_dir = target_dir / target_name / "install"
        self.cc = cc

    @property
    def arch(self) -> str:
        return epics_arch_by_target(self.cc.target)

    def _prepare_source(self, ctx: Context) -> None:
        pass

    def _configure(self, ctx: Context) -> None:
        raise NotImplementedError()

    def _dep_paths(self, ctx: Context) -> List[Path]:
        "Dependent paths."
        return []

    @task
    def build(self, ctx: Context, clean: bool = False) -> None:
        self.cc.install(ctx)

        build_path = ctx.target_path / self.build_dir

        info = _BuildInfo.from_paths(build_path, self._dep_paths(ctx))
        try:
            stored_info = _BuildInfo.load(build_path)
        except (FileNotFoundError, TypeValidationError) as e:
            logger.warning(e)
            clean = True
            pass
        else:
            if not info.has_changed_since(stored_info):
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

        info.store(build_path)

    def _install(self, ctx: Context) -> None:
        raise NotImplementedError()

    @task
    def install(self, ctx: Context) -> None:
        install_path = ctx.target_path / self.install_dir
        logger.info(f"Install from {ctx.target_path / self.build_dir} to {install_path}")
        install_path.mkdir(exist_ok=True)
        self._install(ctx)


class EpicsProjectDeploy(EpicsProject):

    def __init__(
        self,
        *args: Any,
        deploy_path: PurePosixPath,
        blacklist: List[str] = [],
    ) -> None:
        super().__init__(*args)
        self.deploy_path = deploy_path
        self.blacklist = blacklist

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
        ctx.device.store(
            install_path,
            self.deploy_path,
            recursive=True,
            exclude=self.blacklist,
        )
        self._post_deploy(ctx)

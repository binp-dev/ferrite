from __future__ import annotations
from typing import List, overload

import shutil
from pathlib import Path, PurePosixPath
from dataclasses import dataclass

from ferrite.utils.path import TargetPath
from ferrite.utils.run import capture
from ferrite.utils.net import download_alt
from ferrite.components.base import task, Component, Context

import logging

logger = logging.getLogger(__name__)


class Target:

    @overload
    def __init__(self, isa: str, api: str, abi: str, /) -> None:
        ...

    @overload
    def __init__(self, isa: str, vendor: str, api: str, abi: str, /) -> None:
        ...

    def __init__(self, *args: str) -> None:
        if len(args) == 3:
            self.isa, self.api, self.abi = args
            self.vendor = None
        elif len(args) == 4:
            self.isa, self.vendor, self.api, self.abi = args
        else:
            raise TypeError(f"Target() takes 3 or 4 positional arguments but {len(args)} was given")

    @staticmethod
    def from_str(target: str) -> Target:
        return Target(*target.split("-"))

    def __str__(self) -> str:
        return "-".join([
            self.isa,
            *([self.vendor] if self.vendor is not None else []),
            self.api,
            self.abi,
        ])


@dataclass
class Compiler(Component):

    name: str
    target: Target

    @task
    def install(self, ctx: Context) -> None:
        pass

    @task
    def deploy(self, ctx: Context) -> None:
        pass


@dataclass
class Gcc(Compiler):

    @property
    def path(self) -> Path | TargetPath:
        raise NotImplementedError()

    def bin(self, name: str) -> Path | TargetPath:
        raise NotImplementedError()


class GccHost(Gcc):

    def __init__(self) -> None:
        super().__init__("host", Target.from_str(capture(["gcc", "-dumpmachine"])))

    @property
    def path(self) -> Path:
        return Path("/usr")

    def bin(self, name: str) -> Path:
        return self.path / "bin" / name


class GccCross(Gcc):

    def __init__(self, name: str, target: Target, dir_name: str, archive: str, urls: List[str]):
        super().__init__(name, target)

        self.dir_name = dir_name
        self.archive = archive
        self.urls = urls

        self.deploy_path = PurePosixPath("/opt/toolchain")

    @property
    def path(self) -> TargetPath:
        return TargetPath(f"toolchain_{self.dir_name}")

    def bin(self, name: str) -> TargetPath:
        return self.path / "bin" / f"{self.target}-{name}"

    @task
    def install(self, ctx: Context) -> None:
        self_path = ctx.target_path / self.path
        if self_path.exists():
            logger.info(f"Toolchain {self.archive} is already installed")
            return

        tmp_dir = ctx.target_path / "download"
        tmp_dir.mkdir(exist_ok=True)

        archive_path = tmp_dir / self.archive
        if not archive_path.exists():
            logger.info(f"Loading toolchain {self.archive} ...")
            download_alt(self.urls, archive_path)
        else:
            logger.info(f"Toolchain archive {self.archive} already downloaded")

        logger.info(f"Extracting toolchain {self.archive} ...")
        dir_path = tmp_dir / self.dir_name
        try:
            shutil.unpack_archive(archive_path, tmp_dir)
        except:
            if dir_path.exists():
                shutil.rmtree(dir_path)
            raise

        shutil.move(dir_path, self_path)
        shutil.rmtree(tmp_dir)

    @task
    def deploy(self, ctx: Context) -> None:
        assert ctx.device is not None
        src_path = ctx.target_path / self.path / str(self.target)
        logger.info(f"Deploy {src_path} to {ctx.device.name()}:{self.deploy_path}")
        ctx.device.store(
            src_path,
            self.deploy_path,
            recursive=True,
            exclude=["include/*", "*.a", "*.o"],
        )

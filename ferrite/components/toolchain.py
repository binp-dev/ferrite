from __future__ import annotations
from typing import Dict, List, overload

import shutil
from pathlib import Path, PurePosixPath
from dataclasses import dataclass

from ferrite.utils.run import capture
from ferrite.utils.net import download_alt
from ferrite.components.base import Artifact, Component, Task, Context
from ferrite.remote.base import Device

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
class Toolchain(Component):
    name: str
    target: Target
    cached: bool = False


class HostToolchain(Toolchain):

    def __init__(self) -> None:
        super().__init__("host", Target.from_str(capture(["gcc", "-dumpmachine"])))

    def tasks(self) -> Dict[str, Task]:
        return {}


class CrossToolchain(Toolchain):

    class DownloadTask(Task):

        def __init__(self, owner: CrossToolchain) -> None:
            super().__init__()
            self.owner = owner

        def run(self, ctx: Context) -> None:
            self.owner.download()

        def artifacts(self) -> List[Artifact]:
            return [Artifact(self.owner.path, cached=self.owner.cached)]

    class DeployTask(Task):

        def __init__(self, owner: CrossToolchain) -> None:
            super().__init__()
            self.owner = owner

        def run(self, ctx: Context) -> None:
            assert ctx.device is not None
            self.owner.deploy(ctx.device)

    def __init__(self, name: str, target: Target, target_dir: Path, dir_name: str, archive: str, urls: List[str]):
        super().__init__(name, target, cached=True)

        self.target_dir = target_dir

        self.dir_name = dir_name
        self.archive = archive
        self.urls = urls

        self.path = target_dir / f"toolchain_{self.dir_name}"
        self.deploy_path = PurePosixPath("/opt/toolchain")

        self.download_task = self.DownloadTask(self)
        self.deploy_task = self.DeployTask(self)

    def download(self) -> bool:
        if self.path.exists():
            logger.info(f"Toolchain {self.archive} is already downloaded")
            return False

        tmp_dir = self.target_dir / "download"
        tmp_dir.mkdir(exist_ok=True)

        archive_path = tmp_dir / self.archive
        if not archive_path.exists():
            logger.info(f"Loading toolchain {self.archive} ...")
            download_alt(self.urls, archive_path)
        else:
            logger.info(f"Toolchain archive {self.archive} already exists")

        logger.info(f"Extracting toolchain {self.archive} ...")
        dir_path = tmp_dir / self.dir_name
        try:
            shutil.unpack_archive(archive_path, tmp_dir)
        except:
            if dir_path.exists():
                shutil.rmtree(dir_path)
            raise

        shutil.move(dir_path, self.path)

        return True

    def deploy(self, device: Device) -> None:
        src_path = Path(self.path, str(self.target))
        logger.info(f"Deploy {src_path} to {device.name()}:{self.deploy_path}")
        device.store(
            src_path,
            self.deploy_path,
            recursive=True,
            exclude=["include/*", "*.a", "*.o"],
        )

    def tasks(self) -> Dict[str, Task]:
        return {
            "download": self.download_task,
            "deploy": self.deploy_task,
        }

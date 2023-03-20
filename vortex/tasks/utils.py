from __future__ import annotations
from typing import Optional, ClassVar

import os
from time import time
from pathlib import Path
from dataclasses import dataclass, field
import json

from dataclass_type_validator import dataclass_validate, TypeValidationError

import logging

logger = logging.getLogger(__name__)


@dataclass_validate
@dataclass
class TreeModInfo:
    path: Path
    time: float = field(default_factory=time)

    FILE_NAME: ClassVar[str] = ".task.json"

    @staticmethod
    def load(path: Path) -> Optional[TreeModInfo]:
        try:
            with open(path / TreeModInfo.FILE_NAME, "r") as f:
                raw = json.load(f)
            info = TreeModInfo(Path(raw["path"]), raw["time"])
        except (FileNotFoundError, KeyError, TypeValidationError) as e:
            logger.warning(e)
            return None
        if info.path != path:
            return None
        return info

    def store(self) -> None:
        with open(self.path / TreeModInfo.FILE_NAME, "w") as f:
            json.dump({"path": str(self.path), "time": self.time}, f, indent=2, sort_keys=True)

    def newer_than(self, *deps: Path) -> bool:
        return self.time > max([0.0] + [tree_mod_time(d) for d in deps])


def tree_mod_time(path: Path) -> float:
    if path.is_dir():
        info = TreeModInfo.load(path)
        if info is not None:
            return info.time

        max_time = 0.0
        for dirpath, dirnames, filenames in os.walk(path):
            max_time = max(
                [
                    max_time,
                    os.path.getmtime(dirpath),
                    *[os.path.getmtime(os.path.join(dirpath, fn)) for fn in filenames],
                ]
            )
        return max_time
    else:
        return os.path.getmtime(path)

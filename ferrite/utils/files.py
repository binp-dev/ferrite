from __future__ import annotations
from typing import Callable, List, Optional, Set, Tuple

import re
import shutil
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


def substitute(
    rep: List[Tuple[str, str]],
    src: Path,
    dst: Optional[Path] = None,
    force: bool = False,
) -> None:
    if dst is None:
        dst = src

    logger.debug(f"substituting '{src}' -> '{dst}':")

    with open(src, 'r') as file:
        data = file.read()

    new_data = data
    for s, d in rep:
        new_data = re.sub(s, d, new_data, flags=re.M)

    if force or new_data != data:
        logger.debug(f"writing file '{dst}'")
        with open(dst, 'w') as file:
            file.write(new_data)
    else:
        logger.debug(f"file unchanged '{dst}'")


def _inverse_ignore_patterns(ignore_patterns: Callable[[str, List[str]], Set[str]]) -> Callable[[str, List[str]], Set[str]]:

    def allow_patterns(path: str, names: List[str]) -> Set[str]:
        return set(names) - set(ignore_patterns(path, names))

    return allow_patterns


def allow_patterns(*patterns: str) -> Callable[[str, List[str]], Set[str]]:
    return _inverse_ignore_patterns(shutil.ignore_patterns(*patterns))

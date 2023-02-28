from __future__ import annotations
from typing import Any, Sequence, Mapping, List, Optional

import os
from subprocess import Popen, CalledProcessError
from pathlib import Path
from time import sleep
from enum import Enum

from ferrite.components.base import Context

import logging

logger = logging.getLogger(__name__)


class RunMode(Enum):
    NORMAL = 0
    DEBUGGER = 1
    PROFILER = 2


def run(
    ctx: Context,
    args: Sequence[Path | str],
    cwd: Path,
    env: Mapping[str, Path | str] = {},
    mode: RunMode = RunMode.NORMAL,
) -> None:

    if not ctx._running:
        return

    cmd = [str(a) for a in args]
    if mode == RunMode.DEBUGGER:
        cmd = ["gdb", "-batch", "-ex", "run", "-ex", "bt", "-args"] + cmd
    elif mode == RunMode.PROFILER:
        cmd = ["perf", "record"] + cmd
    env = {**dict(os.environ), **{k: str(v) for k, v in env.items()}}
    proc: Optional[Popen[str]] = Popen(cmd, cwd=cwd, env=env, text=True)
    logger.debug(f"Process started: {cmd}")

    assert proc is not None
    while ctx._running:
        sleep(0.1)
        ret = proc.poll()
        if ret is not None:
            proc = None
            if ret != 0:
                raise CalledProcessError(ret, cmd)
            break

    if proc is not None:
        proc.terminate()
        logger.debug(f"Process terminated: {cmd}")

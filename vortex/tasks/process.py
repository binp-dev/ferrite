from __future__ import annotations
from typing import Any, Sequence, Mapping, List, Optional

import os
from subprocess import Popen, CalledProcessError
from pathlib import Path
from time import sleep
from enum import Enum

from vortex.tasks.base import Context

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

    x_args = [str(a) for a in args]
    if mode == RunMode.DEBUGGER:
        x_args = ["gdb", "-batch", "-ex", "run", "-ex", "bt", "-args"] + x_args
    elif mode == RunMode.PROFILER:
        x_args = ["perf", "record"] + x_args
    x_env = {**dict(os.environ), **{k: str(v) for k, v in env.items()}}
    proc: Optional[Popen[str]] = Popen(x_args, cwd=cwd, env=x_env, text=True)
    logger.debug(f"Process started: {x_args}, env={env}")

    assert proc is not None
    while ctx._running:
        sleep(0.1)
        ret = proc.poll()
        if ret is not None:
            proc = None
            if ret != 0:
                raise CalledProcessError(ret, x_args)
            break

    if proc is not None:
        proc.terminate()
        logger.debug(f"Process terminated: {x_args}")

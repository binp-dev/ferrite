from __future__ import annotations
from typing import Optional, Generator

from contextlib import contextmanager

from ferrite.components.base import Context, Task

from colorama import Fore, Style


def run(task: Task, ctx: Context, no_deps: bool = False) -> None:
    ctx.target_path.mkdir(exist_ok=True)

    ctx._stack = []
    ctx._visited = set()
    ctx._guard = with_info
    ctx._no_deps = no_deps

    task(ctx)


@contextmanager
def with_info(task: Task, ctx: Context) -> Generator[None, None, None]:
    tab = ' ' * len(set(ctx._stack))
    print(f"{tab}{Style.BRIGHT + Fore.WHITE}{task.name()}{Style.NORMAL} started ...{Style.RESET_ALL}")
    try:
        yield
    except:
        print(f"{tab}{Style.BRIGHT + Fore.RED}{task.name()}{Style.NORMAL} FAILED:{Style.RESET_ALL}")
    else:
        print(f"{tab}{Style.BRIGHT + Fore.GREEN}{task.name()}{Style.NORMAL} done{Style.RESET_ALL}")

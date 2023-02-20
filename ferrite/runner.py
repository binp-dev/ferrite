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
    depth = len(set(ctx._stack))
    _print_title(f"{' ' * depth}{task.name()} started ...", Style.BRIGHT)
    try:
        yield
    except:
        _print_title(f"{' ' * depth}{task.name()} FAILED:", Style.BRIGHT + Fore.RED)
    else:
        _print_title(f"{' ' * depth}{task.name()} done", Style.BRIGHT + Fore.GREEN)


def _print_title(text: str, style: Optional[str] = None, end: bool = True) -> None:
    if style is not None:
        text = style + text + Style.RESET_ALL
    print(text, flush=True, end=("" if not end else None))

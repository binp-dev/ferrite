from __future__ import annotations

from pathlib import Path

from ferrite.components.git import RepoSource, RepoList


class Freertos(RepoList):

    def __init__(self, dst_dir: Path, branch: str) -> None:
        super().__init__(
            dst_dir,
            [
                RepoSource("https://gitlab.inp.nsk.su/psc/freertos-variscite.git", branch),
                RepoSource("https://github.com/varigit/freertos-variscite.git", branch),
            ],
            cached=True,
        )

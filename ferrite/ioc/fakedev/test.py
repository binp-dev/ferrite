from __future__ import annotations
from typing import List

import time
from pathlib import Path

from ferrite.utils.epics.ioc import make_ioc
import ferrite.utils.epics.ca as ca
from ferrite.ioc.fakedev.base import FakeDev


def assert_eq(a: float, b: float, eps: float = 1e-3) -> None:
    if abs(a - b) > eps:
        raise AssertionError(f"abs({a} - {b}) < {eps}")


class Handler(FakeDev.Handler):

    def __init__(self) -> None:
        self.channels = [0.0, 1.0, -1.0, 3.1415, -10.0, 10.0]

    def write_dac(self, voltage: float) -> None:
        self.channels[0] = voltage

    def read_adcs(self) -> List[float]:
        return self.channels


def assert_synchronized(prefix: Path, handler: Handler) -> None:
    for i, channel in enumerate(handler.channels):
        assert_eq(ca.get(prefix, f"ai{i}"), channel)


def run(epics_base_dir: Path, ioc_dir: Path, arch: str) -> None:

    prefix = epics_base_dir / "bin" / arch
    ioc = make_ioc(ioc_dir, arch)
    handler = Handler()

    scan_period = 1.0
    with FakeDev(prefix, ioc, handler):
        time.sleep(scan_period)
        assert_synchronized(prefix, handler)

        some_val = 2.718
        ca.put(prefix, "ao0", some_val)
        time.sleep(scan_period)
        assert_eq(handler.channels[0], some_val)

        some_val = 1.618
        handler.channels[0] = some_val
        time.sleep(scan_period)
        assert_eq(ca.get(prefix, f"ai0"), some_val)

    print("Test passed!")
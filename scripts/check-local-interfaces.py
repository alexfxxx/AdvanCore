#!/usr/bin/env python3
"""Bounded loopback health check for the primary app and temporary admin UI."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class InterfaceCheck:
    name: str
    url: str


INTERFACES = (
    InterfaceCheck("Primary AdvanCore app", "http://127.0.0.1:8000/api/status"),
    InterfaceCheck("Temporary admin/editing interface", "http://127.0.0.1:8501/_stcore/health"),
)


def check_interfaces(opener=urlopen) -> list[tuple[InterfaceCheck, bool]]:
    results: list[tuple[InterfaceCheck, bool]] = []
    for interface in INTERFACES:
        try:
            with opener(interface.url, timeout=2) as response:
                healthy = 200 <= response.status < 300
        except (HTTPError, URLError, OSError, TimeoutError):
            healthy = False
        results.append((interface, healthy))
    return results


def main() -> int:
    results = check_interfaces()
    for interface, healthy in results:
        print(f"{interface.name}: {'ready' if healthy else 'unavailable'}")
    return 0 if all(healthy for _interface, healthy in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

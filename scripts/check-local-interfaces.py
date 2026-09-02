#!/usr/bin/env python3
"""Bounded health checks for AdvanCore's three loopback interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener


@dataclass(frozen=True)
class InterfaceCheck:
    name: str
    url: str
    expected_status: int = 200
    expected_location: str | None = None


INTERFACES = (
    InterfaceCheck("Primary AdvanCore app", "http://127.0.0.1:8000/api/status"),
    InterfaceCheck(
        "Canonical legacy-port redirect",
        "http://127.0.0.1:8501/",
        expected_status=307,
        expected_location="http://127.0.0.1:8000/",
    ),
    InterfaceCheck(
        "Temporary admin/editing interface",
        "http://127.0.0.1:8502/_stcore/health",
    ),
)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _open_without_redirect(url: str, timeout: int):
    return build_opener(_NoRedirectHandler()).open(url, timeout=timeout)


def _response_is_healthy(interface: InterfaceCheck, response) -> bool:
    if response.status != interface.expected_status:
        return False
    if interface.expected_location is None:
        return True
    return response.headers.get("Location") == interface.expected_location


def check_interfaces(opener=None) -> list[tuple[InterfaceCheck, bool]]:
    request = opener or _open_without_redirect
    results: list[tuple[InterfaceCheck, bool]] = []
    for interface in INTERFACES:
        try:
            with request(interface.url, timeout=2) as response:
                healthy = _response_is_healthy(interface, response)
        except HTTPError as error:
            try:
                healthy = _response_is_healthy(interface, error)
            finally:
                error.close()
        except (URLError, OSError, TimeoutError):
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

#!/usr/bin/env python3
"""Redirect the historical local UI port to AdvanCore's primary console."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


LOOPBACK_HOST = "127.0.0.1"
LEGACY_PORT = 8501
PRIMARY_URL = "http://127.0.0.1:8000/"


class CanonicalRedirectHandler(BaseHTTPRequestHandler):
    """Return one fixed, non-cacheable redirect without reflecting input."""

    protocol_version = "HTTP/1.1"
    server_version = "AdvanCoreRedirect/1.0"
    sys_version = ""

    def _redirect(self) -> None:
        self.send_response(307)
        self.send_header("Location", PRIMARY_URL)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._redirect()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._redirect()

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid retaining local request paths in terminal output."""


def build_server(port: int = LEGACY_PORT) -> ThreadingHTTPServer:
    """Build the loopback-only redirect server; port 0 is allowed for tests."""

    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer between 0 and 65535")
    server = ThreadingHTTPServer((LOOPBACK_HOST, port), CanonicalRedirectHandler)
    server.daemon_threads = True
    return server


def main() -> int:
    server = build_server()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

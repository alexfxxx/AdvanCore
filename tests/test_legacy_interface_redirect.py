"""Focused tests for the loopback-only historical-port redirect."""

from __future__ import annotations

import http.client
import importlib.util
from pathlib import Path
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "redirect-legacy-interface.py"


def _module():
    spec = importlib.util.spec_from_file_location("advancore_legacy_redirect", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def redirect_server():
    module = _module()
    server = module.build_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield module, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_redirect_is_fixed_non_cacheable_and_does_not_reflect_input(
    redirect_server, method
):
    module, port = redirect_server
    connection = http.client.HTTPConnection(module.LOOPBACK_HOST, port, timeout=2)
    try:
        connection.request(method, "/untrusted/path?next=https://example.com")
        response = connection.getresponse()

        assert response.status == 307
        assert response.getheader("Location") == "http://127.0.0.1:8000/"
        assert response.getheader("Cache-Control") == "no-store"
        assert response.read() == b""
    finally:
        connection.close()


def test_redirect_server_is_fixed_to_loopback_and_rejects_invalid_ports():
    module = _module()

    with pytest.raises(ValueError):
        module.build_server(-1)
    with pytest.raises(ValueError):
        module.build_server("8501")

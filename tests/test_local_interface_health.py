import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-local-interfaces.py"


def _module():
    spec = importlib.util.spec_from_file_location("advancore_interface_health", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, status=200, location=None):
        self.status = status
        self.headers = {} if location is None else {"Location": location}

    def __enter__(self): return self
    def __exit__(self, *_args): return False


def test_health_checker_uses_only_fixed_loopback_targets():
    module = _module()
    requested = []

    def opener(url, timeout):
        requested.append((url, timeout))
        if url == "http://127.0.0.1:8501/":
            return _Response(307, "http://127.0.0.1:8000/")
        return _Response(200)

    results = module.check_interfaces(opener)

    assert all(healthy for _interface, healthy in results)
    assert requested == [
        ("http://127.0.0.1:8000/api/status", 2),
        ("http://127.0.0.1:8501/", 2),
        ("http://127.0.0.1:8502/_stcore/health", 2),
    ]


def test_health_checker_rejects_wrong_redirect_destination():
    module = _module()

    def opener(url, _timeout=None, timeout=None):
        if url == "http://127.0.0.1:8501/":
            return _Response(307, "https://example.com/")
        return _Response(200)

    results = module.check_interfaces(opener)

    assert [healthy for _interface, healthy in results] == [True, False, True]


def test_startup_launches_all_interfaces_on_fixed_loopback_ports():
    script = (ROOT / "scripts" / "start-advancore.sh").read_text(encoding="utf-8")

    assert "-m uvicorn main:app" in script
    assert "--host 127.0.0.1 --port 8000" in script
    assert "redirect-legacy-interface.py" in script
    assert "--server.address 127.0.0.1 --server.port 8502" in script
    assert "trap cleanup_interfaces EXIT INT TERM" in script
    assert "0.0.0.0" not in script

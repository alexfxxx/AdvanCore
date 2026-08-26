import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rehearse-advancore-recovery.py"
SPEC = importlib.util.spec_from_file_location("rehearse_advancore_recovery", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Service:
    def __init__(self, fails=False):
        self.fails = fails

    def rehearse_latest(self):
        if self.fails:
            raise RuntimeError("password=never-print")
        return SimpleNamespace(
            backup_id="advancore-safe", table_counts=(("projects", 4),),
            cleanup_confirmed=True,
        )


def test_cli_reports_bounded_success(capsys):
    assert MODULE.main([], service_factory=lambda: Service()) == 0
    output = capsys.readouterr()
    assert "advancore-safe" in output.out
    assert "cleanup confirmed" in output.out
    assert output.err == ""


def test_cli_reports_generic_failure_without_secret(capsys):
    assert MODULE.main([], service_factory=lambda: Service(True)) == 1
    output = capsys.readouterr()
    assert "could not be completed safely" in output.err
    assert "never-print" not in output.err


def test_cli_rejects_arguments_without_running_service(capsys):
    called = False

    def factory():
        nonlocal called
        called = True
        return Service()

    assert MODULE.main(["unexpected"], service_factory=factory) == 2
    assert not called
    assert "accepts no arguments" in capsys.readouterr().err

from advancore.agent_runner.worker_rehearsal import (
    format_multi_worker_rehearsal,
    run_multi_worker_governance_rehearsal,
)


def test_multi_worker_rehearsal_passes_without_launch_or_authority(tmp_path, monkeypatch):
    def launch(*_args, **_kwargs):
        raise AssertionError("offline rehearsal must never launch a process")

    monkeypatch.setattr("advancore.agent_runner.worker.subprocess.Popen", launch)
    report = run_multi_worker_governance_rehearsal(working_directory=tmp_path)
    assert report.passed
    assert report.workers_launched == 0
    assert not report.authority_consumed
    assert len(report.checks) == 9
    assert all(check.passed for check in report.checks)


def test_rehearsal_report_is_bounded_and_contains_no_secret_material(tmp_path):
    rendered = format_multi_worker_rehearsal(
        run_multi_worker_governance_rehearsal(working_directory=tmp_path)
    )
    assert rendered.startswith("Multi-worker governance rehearsal: PASS")
    assert "Workers launched: 0" in rendered
    assert len(rendered.encode("utf-8")) < 4096
    lowered = rendered.lower()
    for forbidden in ("api_key", "password", "bearer ", "stdout", "stderr"):
        assert forbidden not in lowered

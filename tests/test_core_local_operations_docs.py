from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_core_operations_runbook_keeps_checks_and_mutations_separate():
    text = (ROOT / "docs/runbooks/CORE_LOCAL_OPERATIONS.md").read_text(
        encoding="utf-8"
    )
    assert "scripts/check-module-readiness.py" in text
    assert "start-advancore.sh --check-only" in text
    assert "scripts/check-local-interfaces.py" in text
    assert "scripts/backup-advancore.py create" in text
    assert "scripts/rehearse-advancore-recovery.py" in text
    assert "never restores over" in text
    assert "must not delete the database volume" in text


def test_readme_requires_approved_module_brief_before_schema_work():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/check-module-readiness.py" in text
    assert "tasks/MODULE_BRIEF_TEMPLATE.md" in text
    assert "before schema or implementation work" in text

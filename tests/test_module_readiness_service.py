from pathlib import Path
import os
import subprocess
import sys

from advancore.services.module_readiness_service import check_module_foundation


ROOT = Path(__file__).resolve().parents[1]


def test_repository_module_foundation_is_ready():
    result = check_module_foundation(ROOT)
    assert result.ready is True
    assert tuple(item.key for item in result.items) == (
        "module_catalog", "module_brief", "import_contracts"
    )


def test_missing_template_fails_closed_without_paths_in_message(tmp_path: Path):
    result = check_module_foundation(tmp_path)
    item = next(value for value in result.items if value.key == "module_brief")
    assert result.ready is False
    assert item.ready is False
    assert str(tmp_path) not in item.message


def test_template_without_module_identifier_fails_closed(tmp_path: Path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    source = (ROOT / "tasks" / "MODULE_BRIEF_TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    (tasks / "MODULE_BRIEF_TEMPLATE.md").write_text(
        source.replace("MODULE_ID: TODO\n", ""), encoding="utf-8"
    )
    result = check_module_foundation(tmp_path)
    item = next(value for value in result.items if value.key == "module_brief")
    assert item.ready is False


def test_template_module_identifier_must_be_unique_and_top_level(tmp_path: Path):
    source = (ROOT / "tasks" / "MODULE_BRIEF_TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    for index, malformed in enumerate((
        source.replace("MODULE_ID: TODO\n", "MODULE_ID: TODO\nMODULE_ID: TODO\n"),
        source.replace("MODULE_ID: TODO\n", "").replace(
            "## Module identity", "## Module identity\n\nMODULE_ID: TODO"
        ),
        source.replace("STATUS: DRAFT", "status:    draft"),
        source.replace("MODULE_ID: TODO", "MODULE_ID:    TODO"),
    )):
        repository = tmp_path / f"malformed-{index}"
        tasks = repository / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "MODULE_BRIEF_TEMPLATE.md").write_text(
            malformed, encoding="utf-8"
        )
        assert check_module_foundation(repository).ready is False


def test_symlinked_or_oversized_template_fails_closed(tmp_path: Path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    external = tmp_path / "external-template.md"
    external.write_text(
        (ROOT / "tasks" / "MODULE_BRIEF_TEMPLATE.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    template = tasks / "MODULE_BRIEF_TEMPLATE.md"
    template.symlink_to(external)
    assert check_module_foundation(tmp_path).ready is False

    template.unlink()
    template.write_bytes(b"x" * (128 * 1024 + 1))
    assert check_module_foundation(tmp_path).ready is False


def test_fifo_template_and_symlinked_root_ancestor_fail_closed(tmp_path: Path):
    fifo_repo = tmp_path / "fifo-repo"
    fifo_tasks = fifo_repo / "tasks"
    fifo_tasks.mkdir(parents=True)
    os.mkfifo(fifo_tasks / "MODULE_BRIEF_TEMPLATE.md")
    assert check_module_foundation(fifo_repo).ready is False

    real_parent = tmp_path / "real-parent"
    repository = real_parent / "repo"
    tasks = repository / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "MODULE_BRIEF_TEMPLATE.md").write_text(
        (ROOT / "tasks" / "MODULE_BRIEF_TEMPLATE.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    assert check_module_foundation(alias_parent / "repo").ready is False


def test_module_readiness_cli_is_read_only_and_passes():
    completed = subprocess.run(
        [sys.executable, "scripts/check-module-readiness.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stdout.splitlines() == [
        "module_catalog: ready",
        "module_brief: ready",
        "import_contracts: ready",
    ]

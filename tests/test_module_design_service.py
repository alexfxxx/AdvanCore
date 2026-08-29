from pathlib import Path

import pytest

from advancore.services.module_design_service import (
    REQUIRED_MODULE_BRIEF_SECTIONS,
    evaluate_governed_task_module_gate,
    evaluate_module_brief,
)


def _complete_brief() -> str:
    sections = []
    for name in REQUIRED_MODULE_BRIEF_SECTIONS:
        if name == "Facts":
            content = "- FACT: The owner confirmed this synthetic requirement."
        elif name == "Owner decisions":
            content = "None"
        else:
            content = f"Confirmed content for {name.lower()}."
        sections.append(f"## {name}\n\n{content}")
    return (
        "# MODULE — Test\n\nSTATUS: APPROVED\n\nMODULE_ID: fleet\n\n"
        + "\n\n".join(sections)
    )


def test_complete_approved_brief_is_ready():
    result = evaluate_module_brief(_complete_brief())
    assert result.ready is True
    assert result.module_id == "fleet"
    assert result.fact_count == 1
    assert result.missing_sections == ()
    assert result.insubstantial_sections == ()
    assert result.duplicate_sections == ()
    assert result.owner_decision_required is False


def test_draft_missing_or_placeholder_brief_is_not_ready():
    text = _complete_brief().replace("STATUS: APPROVED", "STATUS: DRAFT")
    text = text.replace("Confirmed content for imports.", "TBD")
    text = text.replace("## Reports and filters", "## Removed section")
    result = evaluate_module_brief(text)
    assert result.ready is False
    assert result.status_approved is False
    assert "Imports" in result.placeholder_sections
    assert "Reports and filters" in result.missing_sections


def test_unresolved_owner_decision_blocks_implementation_readiness():
    result = evaluate_module_brief(
        _complete_brief().replace(
            "## Owner decisions\n\nNone",
            "## Owner decisions\n\nConfirm GST treatment.",
        )
    )
    assert result.ready is False
    assert result.owner_decision_required is True


def test_duplicate_required_section_and_noncanonical_status_fail_closed():
    duplicate = _complete_brief() + "\n\n## Owner decisions\n\nNone\n"
    result = evaluate_module_brief(duplicate)
    assert result.ready is False
    assert result.duplicate_sections == ("Owner decisions",)

    misplaced = _complete_brief().replace(
        "STATUS: APPROVED\n\n", "STATUS: DRAFT\n\n"
    ) + "\n\nSTATUS: APPROVED\n"
    result = evaluate_module_brief(misplaced)
    assert result.ready is False
    assert result.status_approved is False


def test_untouched_template_cannot_be_approved_by_changing_status_only():
    template = Path("tasks/MODULE_BRIEF_TEMPLATE.md").read_text(encoding="utf-8")
    result = evaluate_module_brief(template.replace("STATUS: DRAFT", "STATUS: APPROVED"))
    assert result.ready is False
    assert result.fact_count == 0
    assert result.placeholder_sections


def test_short_instruction_like_section_is_not_substantive():
    text = _complete_brief().replace(
        "Confirmed content for required fields.", "x"
    )
    result = evaluate_module_brief(text)
    assert result.ready is False
    assert result.insubstantial_sections == ("Required fields",)


def test_post_programme_task_requires_explicit_module_gate(tmp_path: Path):
    task_text = "# TASK-164 — Test\n\nSTATUS: READY\n"
    missing = evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=tmp_path
    )
    assert missing.ready is False

    non_module = evaluate_governed_task_module_gate(
        task_text
        + "\n## Module design gate\n\n"
        + "Classification: NON_MODULE\n"
        + "Module identifier: None\n"
        + "Approved brief: None\n",
        task_id="TASK-164",
        repository_root=tmp_path,
    )
    assert non_module.ready is True


def test_business_module_task_requires_safe_approved_brief(tmp_path: Path):
    brief_dir = tmp_path / "tasks" / "module-briefs"
    brief_dir.mkdir(parents=True)
    brief_path = brief_dir / "fleet.md"
    brief_path.write_text(_complete_brief(), encoding="utf-8")
    task_text = (
        "# TASK-164 — Fleet\n\nSTATUS: READY\n\n"
        "## Module design gate\n\n"
        "Classification: BUSINESS_MODULE\n"
        "Module identifier: fleet\n"
        "Approved brief: tasks/module-briefs/fleet.md\n"
    )
    result = evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=tmp_path
    )
    assert result.ready is True

    brief_path.write_text(
        _complete_brief().replace("STATUS: APPROVED", "STATUS: DRAFT"),
        encoding="utf-8",
    )
    assert evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=tmp_path
    ).ready is False


def test_business_module_identity_must_match_approved_brief(tmp_path: Path):
    brief_dir = tmp_path / "tasks" / "module-briefs"
    brief_dir.mkdir(parents=True)
    (brief_dir / "fleet.md").write_text(_complete_brief(), encoding="utf-8")
    task_text = (
        "# TASK-164 — Payroll\n\nSTATUS: READY\n\n"
        "## Module design gate\n\n"
        "Classification: BUSINESS_MODULE\n"
        "Module identifier: payroll\n"
        "Approved brief: tasks/module-briefs/fleet.md\n"
    )
    result = evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=tmp_path
    )
    assert result.ready is False
    assert "identities" in result.message


def test_symlinked_brief_directory_and_oversized_brief_fail_closed(tmp_path: Path):
    tasks = tmp_path / "tasks"
    elsewhere = tasks / "approved-elsewhere"
    elsewhere.mkdir(parents=True)
    (elsewhere / "fleet.md").write_text(_complete_brief(), encoding="utf-8")
    (tasks / "module-briefs").symlink_to(elsewhere, target_is_directory=True)
    task_text = (
        "# TASK-164 — Fleet\n\nSTATUS: READY\n\n"
        "## Module design gate\n\n"
        "Classification: BUSINESS_MODULE\n"
        "Module identifier: fleet\n"
        "Approved brief: tasks/module-briefs/fleet.md\n"
    )
    result = evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=tmp_path
    )
    assert result.ready is False
    assert "unsafe" in result.message

    (tasks / "module-briefs").unlink()
    (tasks / "module-briefs").mkdir()
    (tasks / "module-briefs" / "fleet.md").write_bytes(b"x" * (128 * 1024 + 1))
    result = evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=tmp_path
    )
    assert result.ready is False


def test_symlinked_repository_root_fails_closed(tmp_path: Path):
    actual = tmp_path / "actual"
    brief_dir = actual / "tasks" / "module-briefs"
    brief_dir.mkdir(parents=True)
    (brief_dir / "fleet.md").write_text(_complete_brief(), encoding="utf-8")
    alias = tmp_path / "repo-alias"
    alias.symlink_to(actual, target_is_directory=True)
    task_text = (
        "# TASK-164 — Fleet\n\nSTATUS: READY\n\n"
        "## Module design gate\n\n"
        "Classification: BUSINESS_MODULE\n"
        "Module identifier: fleet\n"
        "Approved brief: tasks/module-briefs/fleet.md\n"
    )
    result = evaluate_governed_task_module_gate(
        task_text, task_id="TASK-164", repository_root=alias
    )
    assert result.ready is False
    assert "unsafe" in result.message


@pytest.mark.parametrize("value", ["", "\x00", "x" * (128 * 1024 + 1)])
def test_invalid_or_oversized_brief_fails_closed(value):
    with pytest.raises(ValueError):
        evaluate_module_brief(value)

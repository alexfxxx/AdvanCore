"""Deterministic tests for the TASK-008 runner audit runtime validation artifact.

These tests verify that the supervised runtime validation run was recorded in
the expected document and contains all required sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest


EXPECTED_HEADINGS = [
    "## Purpose",
    "## Expected runner behavior",
    "## Validation result",
    "## Safety observations",
    "## Recommended next step",
]


@pytest.fixture
def validation_doc_path() -> Path:
    return (
        Path(__file__).parent.parent
        / "docs"
        / "validation"
        / "RUNNER_AUDIT_RUNTIME.md"
    )


def test_validation_document_exists(validation_doc_path: Path):
    assert validation_doc_path.exists(), "Runtime validation document must exist"
    assert validation_doc_path.is_file(), "Runtime validation path must be a file"


def test_validation_document_contains_required_headings(validation_doc_path: Path):
    content = validation_doc_path.read_text(encoding="utf-8")
    missing = [heading for heading in EXPECTED_HEADINGS if heading not in content]
    assert not missing, f"Missing required headings: {missing}"

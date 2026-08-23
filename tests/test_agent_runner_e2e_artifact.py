"""Deterministic tests for the TASK-006 E2E validation artifact.

These tests verify that the supervised end-to-end validation run was
recorded in the expected document and contains all required sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest


EXPECTED_HEADINGS = [
    "## Purpose",
    "## Preconditions",
    "## Runner invocation",
    "## Worker boundary",
    "## Validation result",
    "## Safety observations",
    "## Facts",
    "## Assumptions",
    "## Risks / unresolved issues",
    "## Recommended next step",
]


@pytest.fixture
def validation_doc_path() -> Path:
    return Path(__file__).parent.parent / "docs" / "validation" / "AGENT_RUNNER_E2E.md"


def test_validation_document_exists(validation_doc_path: Path):
    assert validation_doc_path.exists(), "E2E validation document must exist"
    assert validation_doc_path.is_file(), "E2E validation path must be a file"


def test_validation_document_contains_required_headings(validation_doc_path: Path):
    content = validation_doc_path.read_text(encoding="utf-8")
    missing = [heading for heading in EXPECTED_HEADINGS if heading not in content]
    assert not missing, f"Missing required headings: {missing}"

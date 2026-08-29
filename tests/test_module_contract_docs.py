from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_module_contracts_preserve_owner_and_migration_boundaries():
    text = (ROOT / "docs/architecture/MODULE_DATA_CONTRACTS.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "registered companies",
        "decimal arithmetic",
        "whether an amount includes GST",
        "preview-first",
        "owner-approved module brief",
        "fresh verified backup",
        "additive migration",
    ):
        assert phrase in text
    assert "Advan is not assumed" in text
    assert "be the owner" in text
    assert "do not authorise a database migration" in text

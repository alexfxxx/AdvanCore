import pytest

from advancore.services.import_contract_registry import (
    ImportContractError,
    ImportDatasetContract,
    get_import_contract,
    import_contracts,
)


def test_existing_dataset_contracts_are_unique_and_approval_gated():
    contracts = import_contracts()
    assert tuple(item.dataset_type for item in contracts) == (
        "vehicles", "drivers", "customers", "routes"
    )
    assert len({item.dataset_type for item in contracts}) == len(contracts)
    assert all(item.preview_only_until_approved for item in contracts)
    assert get_import_contract("vehicles").identity_field == "registration_number"


def test_unknown_dataset_fails_closed():
    with pytest.raises(ImportContractError, match="not supported"):
        get_import_contract("finance")


def test_contract_cannot_disable_approval_or_use_unknown_identity():
    with pytest.raises(ImportContractError):
        ImportDatasetContract("sample", "Sample", ("name",), "missing")
    with pytest.raises(ImportContractError, match="cannot be disabled"):
        ImportDatasetContract(
            "sample", "Sample", ("name",), "name",
            preview_only_until_approved=False,
        )

"""Code-owned contracts for preview-first operational imports."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping


_DATASET_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_FIELD = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ImportContractError(ValueError):
    """Raised when an import contract identity is unknown or malformed."""


@dataclass(frozen=True)
class ImportDatasetContract:
    dataset_type: str
    label: str
    headers: tuple[str, ...]
    identity_field: str
    preview_only_until_approved: bool = True

    def __post_init__(self) -> None:
        if not _DATASET_ID.fullmatch(self.dataset_type):
            raise ImportContractError("Import dataset identifier is invalid")
        if not isinstance(self.label, str) or not self.label.strip() or len(self.label) > 60:
            raise ImportContractError("Import dataset label is invalid")
        if (
            not isinstance(self.headers, tuple)
            or not self.headers
            or len(set(self.headers)) != len(self.headers)
            or any(not isinstance(value, str) or not _FIELD.fullmatch(value) for value in self.headers)
        ):
            raise ImportContractError("Import headers are invalid")
        if self.identity_field not in self.headers:
            raise ImportContractError("Import identity field is not a declared header")
        if self.preview_only_until_approved is not True:
            raise ImportContractError("Import publication approval cannot be disabled")


_CONTRACTS: tuple[ImportDatasetContract, ...] = (
    ImportDatasetContract(
        "vehicles", "Vehicles", ("registration_number", "make_model"),
        "registration_number",
    ),
    ImportDatasetContract(
        "drivers", "Drivers", ("name", "employee_reference"),
        "employee_reference",
    ),
    ImportDatasetContract(
        "customers", "Customers", ("name", "customer_reference"),
        "customer_reference",
    ),
    ImportDatasetContract(
        "routes", "Routes", ("route_code", "origin", "destination"),
        "route_code",
    ),
)
_BY_TYPE: Mapping[str, ImportDatasetContract] = MappingProxyType(
    {contract.dataset_type: contract for contract in _CONTRACTS}
)
if len(_BY_TYPE) != len(_CONTRACTS):
    raise ImportContractError("Duplicate import dataset contract")


def import_contracts() -> tuple[ImportDatasetContract, ...]:
    return _CONTRACTS


def get_import_contract(dataset_type: str) -> ImportDatasetContract:
    if not isinstance(dataset_type, str) or dataset_type not in _BY_TYPE:
        raise ImportContractError("The selected CSV dataset type is not supported")
    return _BY_TYPE[dataset_type]

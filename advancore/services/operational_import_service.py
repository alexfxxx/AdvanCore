"""Preview-only CSV intake for transport operational master data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
import re


MAX_CSV_BYTES = 1_048_576
MAX_CSV_ROWS = 1_000

DATASET_HEADERS: dict[str, tuple[str, ...]] = {
    "vehicles": ("registration_number", "make_model"),
    "drivers": ("name", "employee_reference"),
    "customers": ("name", "customer_reference"),
    "routes": ("route_code", "origin", "destination"),
}

DATASET_LABELS: dict[str, str] = {
    "vehicles": "Vehicles",
    "drivers": "Drivers",
    "customers": "Customers",
    "routes": "Routes",
}

_REGISTRATION = re.compile(r"[A-Z0-9][A-Z0-9 -]{0,31}")


class OperationalImportError(ValueError):
    """Raised when a CSV cannot safely produce a preview."""


@dataclass(frozen=True)
class ImportRowPreview:
    row_number: int
    values: dict[str, str | None]
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class OperationalImportPreview:
    dataset_type: str
    headers: tuple[str, ...]
    rows: tuple[ImportRowPreview, ...]

    @property
    def valid_row_count(self) -> int:
        return sum(row.is_valid for row in self.rows)

    @property
    def invalid_row_count(self) -> int:
        return len(self.rows) - self.valid_row_count


def _headers(dataset_type: str) -> tuple[str, ...]:
    try:
        return DATASET_HEADERS[dataset_type]
    except KeyError as exc:
        raise OperationalImportError("The selected CSV dataset type is not supported.") from exc


def csv_template(dataset_type: str) -> bytes:
    """Return a stable, header-only UTF-8 CSV template."""
    output = StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(_headers(dataset_type))
    return output.getvalue().encode("utf-8")


def _vehicle(values: dict[str, str]) -> tuple[dict[str, str | None], tuple[str, ...]]:
    errors: list[str] = []
    registration = " ".join(values["registration_number"].strip().upper().split())
    make_model = values["make_model"].strip() or None
    if not _REGISTRATION.fullmatch(registration):
        errors.append("Registration number must use 1–32 letters, numbers, spaces, or hyphens.")
    if make_model is not None and len(make_model) > 120:
        errors.append("Make/model must be 120 characters or fewer.")
    return {"registration_number": registration, "make_model": make_model}, tuple(errors)


def _driver(values: dict[str, str]) -> tuple[dict[str, str | None], tuple[str, ...]]:
    errors: list[str] = []
    name = " ".join(values["name"].strip().split())
    reference = values["employee_reference"].strip().upper() or None
    if not name or len(name) > 120:
        errors.append("Driver name must be 1–120 characters.")
    if reference is not None and (
        len(reference) > 40 or any(character in reference for character in "\r\n\t")
    ):
        errors.append("Employee reference must be 40 characters or fewer.")
    return {"name": name, "employee_reference": reference}, tuple(errors)


def _customer(values: dict[str, str]) -> tuple[dict[str, str | None], tuple[str, ...]]:
    errors: list[str] = []
    name = " ".join(values["name"].strip().split())
    reference = values["customer_reference"].strip().upper() or None
    if not name or len(name) > 160:
        errors.append("Customer name must be 1–160 characters.")
    if reference is not None and (
        len(reference) > 40 or any(character in reference for character in "\r\n\t")
    ):
        errors.append("Customer reference must be 40 characters or fewer.")
    return {"name": name, "customer_reference": reference}, tuple(errors)


def _route(values: dict[str, str]) -> tuple[dict[str, str | None], tuple[str, ...]]:
    errors: list[str] = []
    code = values["route_code"].strip().upper()
    origin = " ".join(values["origin"].split())
    destination = " ".join(values["destination"].split())
    if not code or len(code) > 40:
        errors.append("Route code must be 1–40 characters.")
    if not origin or not destination or len(origin) > 160 or len(destination) > 160:
        errors.append("Origin and destination are required and must be 160 characters or fewer.")
    if origin and destination and origin.casefold() == destination.casefold():
        errors.append("Origin and destination must be different.")
    return {"route_code": code, "origin": origin, "destination": destination}, tuple(errors)


_VALIDATORS = {
    "vehicles": _vehicle,
    "drivers": _driver,
    "customers": _customer,
    "routes": _route,
}


def preview_csv(dataset_type: str, content: bytes) -> OperationalImportPreview:
    """Parse and validate CSV bytes without persistence or external calls."""
    expected_headers = _headers(dataset_type)
    if not isinstance(content, bytes):
        raise OperationalImportError("CSV content must be supplied as bytes.")
    if len(content) > MAX_CSV_BYTES:
        raise OperationalImportError("CSV file exceeds the 1 MiB preview limit.")
    try:
        decoded = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise OperationalImportError("CSV file must be valid UTF-8.") from exc

    try:
        reader = csv.reader(StringIO(decoded, newline=""), strict=True)
        supplied_headers = tuple(next(reader))
    except StopIteration as exc:
        raise OperationalImportError("CSV file is empty and has no header row.") from exc
    except csv.Error as exc:
        raise OperationalImportError("CSV file is malformed.") from exc

    if len(set(supplied_headers)) != len(supplied_headers):
        raise OperationalImportError("CSV header contains duplicate column names.")
    if supplied_headers != expected_headers:
        expected = ", ".join(expected_headers)
        raise OperationalImportError(f"CSV headers must be exactly: {expected}.")

    previews: list[ImportRowPreview] = []
    validator = _VALIDATORS[dataset_type]
    try:
        for row_number, row in enumerate(reader, start=2):
            if len(previews) >= MAX_CSV_ROWS:
                raise OperationalImportError(
                    f"CSV file exceeds the {MAX_CSV_ROWS:,}-row preview limit."
                )
            if len(row) != len(expected_headers):
                previews.append(
                    ImportRowPreview(
                        row_number=row_number,
                        values={header: None for header in expected_headers},
                        errors=(f"Row must contain exactly {len(expected_headers)} columns.",),
                    )
                )
                continue
            raw_values = dict(zip(expected_headers, row, strict=True))
            normalized, errors = validator(raw_values)
            previews.append(
                ImportRowPreview(
                    row_number=row_number,
                    values=normalized,
                    errors=errors,
                )
            )
    except csv.Error as exc:
        raise OperationalImportError("CSV file is malformed.") from exc

    return OperationalImportPreview(
        dataset_type=dataset_type,
        headers=expected_headers,
        rows=tuple(previews),
    )

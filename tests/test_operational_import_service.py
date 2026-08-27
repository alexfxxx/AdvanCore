import pytest

from advancore.services.operational_import_service import (
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    OperationalImportError,
    csv_template,
    preview_csv,
)


@pytest.mark.parametrize(
    ("dataset_type", "expected"),
    [
        ("vehicles", b"registration_number,make_model\n"),
        ("drivers", b"name,employee_reference\n"),
        ("customers", b"name,customer_reference\n"),
        ("routes", b"route_code,origin,destination\n"),
    ],
)
def test_stable_header_only_templates(dataset_type, expected):
    assert csv_template(dataset_type) == expected


@pytest.mark.parametrize(
    ("dataset_type", "content", "expected_values"),
    [
        (
            "vehicles",
            b"registration_number,make_model\n sgp 123-a ,Bus Model\n",
            {"registration_number": "SGP 123-A", "make_model": "Bus Model"},
        ),
        (
            "drivers",
            b"name,employee_reference\n Alex  Tan , emp-1 \n",
            {"name": "Alex Tan", "employee_reference": "EMP-1"},
        ),
        (
            "customers",
            b"name,customer_reference\n Example School , sch-1 \n",
            {"name": "Example School", "customer_reference": "SCH-1"},
        ),
        (
            "routes",
            b"route_code,origin,destination\n r-1 , North Depot , South Terminal \n",
            {"route_code": "R-1", "origin": "North Depot", "destination": "South Terminal"},
        ),
    ],
)
def test_valid_rows_are_normalized_for_preview(dataset_type, content, expected_values):
    preview = preview_csv(dataset_type, content)

    assert preview.valid_row_count == 1
    assert preview.invalid_row_count == 0
    assert preview.rows[0].row_number == 2
    assert preview.rows[0].values == expected_values


@pytest.mark.parametrize(
    ("dataset_type", "content", "message"),
    [
        ("unknown", b"header\n", "not supported"),
        ("vehicles", b"\xff", "valid UTF-8"),
        ("vehicles", b"", "empty"),
        ("vehicles", b"registration_number,registration_number\nA,B\n", "duplicate"),
        ("vehicles", b"make_model,registration_number\nBus,A\n", "headers must be exactly"),
        ("routes", b'route_code,origin,destination\n"unterminated', "malformed"),
    ],
)
def test_structural_failures_are_closed(dataset_type, content, message):
    with pytest.raises(OperationalImportError, match=message):
        preview_csv(dataset_type, content)


def test_oversized_files_and_excessive_rows_fail_closed():
    with pytest.raises(OperationalImportError, match="1 MiB"):
        preview_csv("vehicles", b"x" * (MAX_CSV_BYTES + 1))

    content = b"name,employee_reference\n" + b"Driver,\n" * (MAX_CSV_ROWS + 1)
    with pytest.raises(OperationalImportError, match="1,000-row"):
        preview_csv("drivers", content)


@pytest.mark.parametrize(
    ("dataset_type", "content", "message"),
    [
        ("vehicles", b"registration_number,make_model\n!,Bus\n", "Registration number"),
        ("drivers", b"name,employee_reference\n,REF\n", "Driver name"),
        ("customers", b"name,customer_reference\n,REF\n", "Customer name"),
        ("routes", b"route_code,origin,destination\nR1,Same,Same\n", "must be different"),
    ],
)
def test_invalid_domain_values_are_row_level_results(dataset_type, content, message):
    preview = preview_csv(dataset_type, content)

    assert preview.valid_row_count == 0
    assert preview.invalid_row_count == 1
    assert message in " ".join(preview.rows[0].errors)


def test_wrong_column_count_is_a_row_level_error_without_values():
    preview = preview_csv("routes", b"route_code,origin,destination\nR1,Depot\n")

    assert preview.invalid_row_count == 1
    assert preview.rows[0].values == {
        "route_code": None,
        "origin": None,
        "destination": None,
    }
    assert preview.rows[0].errors == ("Row must contain exactly 3 columns.",)

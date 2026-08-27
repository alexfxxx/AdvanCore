from advancore.services.operational_import_review_service import (
    REVIEW_ALREADY_EXISTS,
    REVIEW_DUPLICATE_FILE,
    REVIEW_DUPLICATE_FILE_AND_EXISTS,
    REVIEW_INVALID,
    REVIEW_READY,
    review_import,
)
from advancore.services.operational_import_service import preview_csv


def test_review_flags_every_in_file_duplicate_and_existing_identity():
    preview = preview_csv(
        "vehicles",
        b"registration_number,make_model\nBUS-1,Model A\nBUS-1,Model B\nBUS-2,Model C\nBUS-3,Model D\n",
    )

    review = review_import(preview, {"BUS-2"})

    assert [row.status for row in review.rows] == [
        REVIEW_DUPLICATE_FILE,
        REVIEW_DUPLICATE_FILE,
        REVIEW_ALREADY_EXISTS,
        REVIEW_READY,
    ]
    assert review.publishable_count == 1


def test_invalid_rows_remain_blocked():
    preview = preview_csv("routes", b"route_code,origin,destination\nR1,Same,Same\n")

    review = review_import(preview, set())

    assert review.rows[0].status == REVIEW_INVALID
    assert not review.rows[0].publishable


def test_missing_optional_reference_is_not_inferred_as_duplicate():
    preview = preview_csv(
        "drivers",
        b"name,employee_reference\nDriver One,\nDriver One,\n",
    )

    review = review_import(preview, set())

    assert [row.status for row in review.rows] == [REVIEW_READY, REVIEW_READY]


def test_exact_optional_reference_matches_are_normalized_by_preview():
    preview = preview_csv("customers", b"name,customer_reference\nSchool, ref-1 \n")

    review = review_import(preview, {"REF-1"})

    assert review.rows[0].status == REVIEW_ALREADY_EXISTS


def test_review_preserves_file_and_database_duplicate_reasons_together():
    preview = preview_csv(
        "routes",
        b"route_code,origin,destination\nR1,North,South\nR1,East,West\n",
    )

    review = review_import(preview, {"R1"})

    assert [row.status for row in review.rows] == [
        REVIEW_DUPLICATE_FILE_AND_EXISTS,
        REVIEW_DUPLICATE_FILE_AND_EXISTS,
    ]
    assert all("more than once" in row.message for row in review.rows)
    assert all("already exists" in row.message for row in review.rows)

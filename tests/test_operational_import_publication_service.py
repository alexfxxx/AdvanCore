import pytest

from advancore.services.operational_import_publication_service import (
    ImportPublicationError,
    publish_import,
)
from advancore.services.operational_import_review_service import review_import
from advancore.services.operational_import_service import preview_csv


def _ready_review():
    return review_import(
        preview_csv(
            "vehicles",
            b"registration_number,make_model\nTEST-1,Model One\nTEST-2,Model Two\n",
        ),
        set(),
    )


def test_confirmation_is_required_before_callback_runs():
    calls = []
    with pytest.raises(ImportPublicationError, match="confirmation"):
        publish_import(_ready_review(), confirmed=False, create_record=calls.append)
    assert calls == []


def test_any_blocked_row_prevents_the_whole_batch():
    review = review_import(
        preview_csv(
            "routes",
            b"route_code,origin,destination\nR1,North,South\nR1,East,West\n",
        ),
        set(),
    )
    calls = []

    with pytest.raises(ImportPublicationError, match="Every row"):
        publish_import(review, confirmed=True, create_record=calls.append)

    assert calls == []


def test_ready_batch_is_published_in_order():
    calls = []

    result = publish_import(_ready_review(), confirmed=True, create_record=calls.append)

    assert result.published_count == 2
    assert [item["registration_number"] for item in calls] == ["TEST-1", "TEST-2"]


def test_empty_batch_fails_closed():
    review = review_import(preview_csv("customers", b"name,customer_reference\n"), set())

    with pytest.raises(ImportPublicationError, match="no rows"):
        publish_import(review, confirmed=True, create_record=lambda _values: None)

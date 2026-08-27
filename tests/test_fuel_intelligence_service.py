from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from advancore.services.fuel_intelligence_service import (
    FuelIntelligenceError,
    FuelIntelligenceService,
)


class Repository:
    def __init__(self, entries):
        self.entries = entries

    def list(self):
        return self.entries


def entry(identifier, vehicle, day, litres, cost=None, odometer=None):
    return SimpleNamespace(
        id=identifier,
        vehicle_id=vehicle,
        recorded_on=day,
        litres=Decimal(litres),
        total_cost=None if cost is None else Decimal(cost),
        odometer_km=None if odometer is None else Decimal(odometer),
    )


def test_summary_uses_only_recorded_facts_and_daily_totals():
    service = FuelIntelligenceService(
        Repository(
            [
                entry(1, 1, date(2026, 8, 1), "20", "40", "1000"),
                entry(2, 1, date(2026, 8, 2), "30", None, "1120"),
                entry(3, 2, date(2026, 8, 2), "10", "30", "500"),
                entry(4, 2, date(2026, 8, 3), "15", "30", "480"),
            ]
        )
    )

    summary = service.get_summary()

    assert summary.entry_count == 4
    assert summary.total_litres == Decimal("75")
    assert summary.cost_entry_count == 3
    assert summary.total_cost == Decimal("100")
    assert summary.average_cost_per_litre == Decimal("2.22")
    assert [(item.recorded_on, item.litres) for item in summary.daily_totals] == [
        (date(2026, 8, 1), Decimal("20")),
        (date(2026, 8, 2), Decimal("40")),
        (date(2026, 8, 3), Decimal("15")),
    ]
    assert summary.observed_distance_km == Decimal("120")
    assert summary.observed_distance_interval_count == 1
    assert summary.ignored_odometer_interval_count == 1


def test_empty_summary_keeps_optional_measures_unavailable():
    summary = FuelIntelligenceService(Repository([])).get_summary()

    assert summary.entry_count == 0
    assert summary.total_litres == Decimal("0")
    assert summary.total_cost is None
    assert summary.average_cost_per_litre is None
    assert summary.observed_distance_km is None
    assert summary.daily_totals == ()


def test_invalid_stored_fact_fails_closed():
    invalid = entry(1, 1, date(2026, 8, 1), "-1")

    with pytest.raises(FuelIntelligenceError, match="litres"):
        FuelIntelligenceService(Repository([invalid])).get_summary()


@pytest.mark.parametrize(
    "entries",
    [
        [
            entry(1, 1, date(2026, 8, 1), "10", odometer="100"),
            entry(2, 1, date(2026, 8, 1), "10", odometer="200"),
        ],
        [
            entry(1, 1, date(2026, 8, 1), "10", odometer="200"),
            entry(2, 1, date(2026, 8, 1), "10", odometer="100"),
        ],
    ],
)
def test_same_day_odometer_order_is_ambiguous_in_both_insertion_orders(entries):
    summary = FuelIntelligenceService(Repository(entries)).get_summary()

    assert summary.observed_distance_km is None
    assert summary.observed_distance_interval_count == 0
    assert summary.ignored_odometer_interval_count == 1

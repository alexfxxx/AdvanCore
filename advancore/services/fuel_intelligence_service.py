"""Read-only intelligence derived strictly from recorded fuel facts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from advancore.repositories import FuelEntryRepository


class FuelIntelligenceError(ValueError):
    """Raised when stored fuel evidence is invalid or ambiguous."""


@dataclass(frozen=True)
class FuelDailyTotal:
    recorded_on: date
    litres: Decimal


@dataclass(frozen=True)
class FuelIntelligenceSummary:
    entry_count: int
    total_litres: Decimal
    cost_entry_count: int
    total_cost: Decimal | None
    average_cost_per_litre: Decimal | None
    odometer_reading_count: int
    observed_distance_km: Decimal | None
    observed_distance_interval_count: int
    ignored_odometer_interval_count: int
    daily_totals: tuple[FuelDailyTotal, ...]


def _decimal(value: object, label: str, *, positive: bool) -> Decimal:
    if isinstance(value, bool):
        raise FuelIntelligenceError(f"Stored {label} is invalid.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise FuelIntelligenceError(f"Stored {label} is invalid.") from None
    if not number.is_finite() or (number <= 0 if positive else number < 0):
        raise FuelIntelligenceError(f"Stored {label} is invalid.")
    return number


class FuelIntelligenceService:
    def __init__(self, repository: FuelEntryRepository):
        self._repository = repository

    def get_summary(self) -> FuelIntelligenceSummary:
        entries = list(self._repository.list())
        total_litres = Decimal("0")
        total_cost = Decimal("0")
        costed_litres = Decimal("0")
        cost_entry_count = 0
        daily_litres: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        odometer_by_vehicle: dict[int, list[tuple[date, int, Decimal]]] = defaultdict(list)

        for entry in entries:
            recorded_on = getattr(entry, "recorded_on", None)
            vehicle_id = getattr(entry, "vehicle_id", None)
            identifier = getattr(entry, "id", None)
            if type(recorded_on) is not date:
                raise FuelIntelligenceError("Stored fuel date is invalid.")
            if isinstance(vehicle_id, bool) or not isinstance(vehicle_id, int) or vehicle_id <= 0:
                raise FuelIntelligenceError("Stored fuel vehicle is invalid.")
            if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
                raise FuelIntelligenceError("Stored fuel identifier is invalid.")
            litres = _decimal(getattr(entry, "litres", None), "fuel litres", positive=True)
            total_litres += litres
            daily_litres[recorded_on] += litres

            raw_cost = getattr(entry, "total_cost", None)
            if raw_cost is not None:
                cost = _decimal(raw_cost, "fuel cost", positive=False)
                total_cost += cost
                costed_litres += litres
                cost_entry_count += 1

            raw_odometer = getattr(entry, "odometer_km", None)
            if raw_odometer is not None:
                odometer = _decimal(raw_odometer, "fuel odometer", positive=False)
                odometer_by_vehicle[vehicle_id].append((recorded_on, identifier, odometer))

        observed_distance = Decimal("0")
        observed_intervals = 0
        ignored_intervals = 0
        odometer_reading_count = sum(len(readings) for readings in odometer_by_vehicle.values())
        for readings in odometer_by_vehicle.values():
            readings_by_date: dict[date, list[Decimal]] = defaultdict(list)
            for recorded_on, _identifier, odometer in readings:
                readings_by_date[recorded_on].append(odometer)
            ordered_dates = sorted(readings_by_date)
            ignored_intervals += sum(
                max(0, len(readings_by_date[recorded_on]) - 1)
                for recorded_on in ordered_dates
            )
            for previous_date, current_date in zip(ordered_dates, ordered_dates[1:]):
                previous_readings = readings_by_date[previous_date]
                current_readings = readings_by_date[current_date]
                if len(previous_readings) != 1 or len(current_readings) != 1:
                    ignored_intervals += 1
                    continue
                difference = current_readings[0] - previous_readings[0]
                if difference > 0:
                    observed_distance += difference
                    observed_intervals += 1
                else:
                    ignored_intervals += 1

        average_cost = None
        if cost_entry_count:
            average_cost = (total_cost / costed_litres).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return FuelIntelligenceSummary(
            entry_count=len(entries),
            total_litres=total_litres,
            cost_entry_count=cost_entry_count,
            total_cost=total_cost if cost_entry_count else None,
            average_cost_per_litre=average_cost,
            odometer_reading_count=odometer_reading_count,
            observed_distance_km=observed_distance if observed_intervals else None,
            observed_distance_interval_count=observed_intervals,
            ignored_odometer_interval_count=ignored_intervals,
            daily_totals=tuple(
                FuelDailyTotal(recorded_on, daily_litres[recorded_on])
                for recorded_on in sorted(daily_litres)
            ),
        )

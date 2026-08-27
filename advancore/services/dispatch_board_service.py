"""Truthful read-only daily dispatch projection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DispatchBoardRow:
    trip_id: int
    trip_reference: str
    trip_status: str
    route_label: str
    dispatch_state: str
    vehicle_label: str
    driver_label: str
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class AvailableResource:
    identifier: int
    label: str


@dataclass(frozen=True)
class DispatchBoard:
    service_date: date
    rows: tuple[DispatchBoardRow, ...]
    available_vehicles: tuple[AvailableResource, ...]
    available_drivers: tuple[AvailableResource, ...]

    def state_count(self, state: str) -> int:
        return sum(row.dispatch_state == state for row in self.rows)

    @property
    def conflict_count(self) -> int:
        return sum(bool(row.conflicts) for row in self.rows)


def _by_id(records: Sequence[object]) -> dict[int, object]:
    return {
        identifier: record
        for record in records
        if isinstance((identifier := getattr(record, "id", None)), int)
    }


def build_dispatch_board(
    service_date: date,
    *,
    trips: Sequence[object],
    assignments: Sequence[object],
    routes: Sequence[object],
    vehicles: Sequence[object],
    drivers: Sequence[object],
) -> DispatchBoard:
    """Project recorded state for one date without mutating source records."""
    daily_trips = [trip for trip in trips if getattr(trip, "service_date", None) == service_date]
    daily_trip_ids = {getattr(trip, "id", None) for trip in daily_trips}
    daily_assignments = [
        item for item in assignments if getattr(item, "trip_id", None) in daily_trip_ids
    ]
    assignment_by_trip = {getattr(item, "trip_id"): item for item in daily_assignments}
    active_assignments = [
        item for item in daily_assignments if getattr(item, "status", None) == "assigned"
    ]
    vehicle_use = Counter(getattr(item, "vehicle_id", None) for item in active_assignments)
    driver_use = Counter(getattr(item, "driver_id", None) for item in active_assignments)
    route_by_id = _by_id(routes)
    vehicle_by_id = _by_id(vehicles)
    driver_by_id = _by_id(drivers)

    rows: list[DispatchBoardRow] = []
    for trip in sorted(
        daily_trips,
        key=lambda item: (str(getattr(item, "trip_reference", "")).casefold(), getattr(item, "id", 0)),
    ):
        trip_id = getattr(trip, "id")
        assignment = assignment_by_trip.get(trip_id)
        route_id = getattr(trip, "route_id", None)
        route = route_by_id.get(route_id)
        route_label = (
            f"{route.route_code}: {route.origin} → {route.destination}"
            if route is not None
            else f"Missing route #{route_id}"
        )
        conflicts: list[str] = []
        if assignment is None:
            dispatch_state = "Unassigned"
            vehicle_label = "Not assigned"
            driver_label = "Not assigned"
        else:
            assignment_status = str(getattr(assignment, "status", "unknown"))
            dispatch_state = assignment_status.replace("_", " ").title()
            vehicle_id = getattr(assignment, "vehicle_id", None)
            driver_id = getattr(assignment, "driver_id", None)
            vehicle = vehicle_by_id.get(vehicle_id)
            driver = driver_by_id.get(driver_id)
            vehicle_label = (
                vehicle.registration_number if vehicle is not None else f"Missing vehicle #{vehicle_id}"
            )
            driver_label = driver.name if driver is not None else f"Missing driver #{driver_id}"
            if assignment_status == "assigned" and vehicle_use[vehicle_id] > 1:
                conflicts.append("Vehicle has multiple active assignments on this date.")
            if assignment_status == "assigned" and driver_use[driver_id] > 1:
                conflicts.append("Driver has multiple active assignments on this date.")
        rows.append(
            DispatchBoardRow(
                trip_id=trip_id,
                trip_reference=str(getattr(trip, "trip_reference", "")),
                trip_status=str(getattr(trip, "status", "unknown")),
                route_label=route_label,
                dispatch_state=dispatch_state,
                vehicle_label=vehicle_label,
                driver_label=driver_label,
                conflicts=tuple(conflicts),
            )
        )

    used_vehicle_ids = {getattr(item, "vehicle_id", None) for item in active_assignments}
    used_driver_ids = {getattr(item, "driver_id", None) for item in active_assignments}
    available_vehicles = tuple(
        AvailableResource(record.id, record.registration_number)
        for record in sorted(vehicles, key=lambda item: item.registration_number.casefold())
        if getattr(record, "status", None) == "active" and record.id not in used_vehicle_ids
    )
    available_drivers = tuple(
        AvailableResource(record.id, record.name)
        for record in sorted(drivers, key=lambda item: item.name.casefold())
        if getattr(record, "status", None) == "active" and record.id not in used_driver_ids
    )
    return DispatchBoard(
        service_date=service_date,
        rows=tuple(rows),
        available_vehicles=available_vehicles,
        available_drivers=available_drivers,
    )

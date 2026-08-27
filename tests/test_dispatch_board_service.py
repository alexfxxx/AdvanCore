from datetime import date
from types import SimpleNamespace

from advancore.services.dispatch_board_service import build_dispatch_board


DAY = date(2026, 8, 27)


def item(**values):
    return SimpleNamespace(**values)


def test_board_filters_date_and_reports_assignment_states_and_availability():
    trips = [
        item(id=1, trip_reference="T1", route_id=10, service_date=DAY, status="planned"),
        item(id=2, trip_reference="T2", route_id=10, service_date=DAY, status="planned"),
        item(id=3, trip_reference="T3", route_id=10, service_date=DAY, status="planned"),
        item(id=4, trip_reference="OTHER", route_id=10, service_date=date(2026, 8, 28), status="planned"),
    ]
    assignments = [
        item(trip_id=1, vehicle_id=20, driver_id=30, status="assigned"),
        item(trip_id=2, vehicle_id=21, driver_id=31, status="released"),
    ]
    board = build_dispatch_board(
        DAY,
        trips=trips,
        assignments=assignments,
        routes=[item(id=10, route_code="R1", origin="North", destination="South")],
        vehicles=[
            item(id=20, registration_number="BUS-1", status="active"),
            item(id=21, registration_number="BUS-2", status="active"),
        ],
        drivers=[
            item(id=30, name="Driver One", status="active"),
            item(id=31, name="Driver Two", status="active"),
        ],
    )

    assert [row.trip_reference for row in board.rows] == ["T1", "T2", "T3"]
    assert [row.dispatch_state for row in board.rows] == ["Assigned", "Released", "Unassigned"]
    assert [resource.label for resource in board.available_vehicles] == ["BUS-2"]
    assert [resource.label for resource in board.available_drivers] == ["Driver Two"]


def test_board_flags_every_row_in_exact_same_day_resource_conflict():
    trips = [
        item(id=1, trip_reference="T1", route_id=10, service_date=DAY, status="planned"),
        item(id=2, trip_reference="T2", route_id=10, service_date=DAY, status="planned"),
    ]
    assignments = [
        item(trip_id=1, vehicle_id=20, driver_id=30, status="assigned"),
        item(trip_id=2, vehicle_id=20, driver_id=30, status="assigned"),
    ]
    board = build_dispatch_board(
        DAY,
        trips=trips,
        assignments=assignments,
        routes=[item(id=10, route_code="R1", origin="North", destination="South")],
        vehicles=[item(id=20, registration_number="BUS-1", status="active")],
        drivers=[item(id=30, name="Driver One", status="active")],
    )

    assert board.conflict_count == 2
    assert all(len(row.conflicts) == 2 for row in board.rows)
    assert board.available_vehicles == ()
    assert board.available_drivers == ()


def test_board_labels_missing_relations_without_inference():
    trip = item(id=1, trip_reference="T1", route_id=99, service_date=DAY, status="planned")
    assignment = item(trip_id=1, vehicle_id=98, driver_id=97, status="assigned")

    board = build_dispatch_board(
        DAY,
        trips=[trip],
        assignments=[assignment],
        routes=[],
        vehicles=[],
        drivers=[],
    )

    assert board.rows[0].route_label == "Missing route #99"
    assert board.rows[0].vehicle_label == "Missing vehicle #98"
    assert board.rows[0].driver_label == "Missing driver #97"

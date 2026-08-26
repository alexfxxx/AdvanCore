"""Truthful owner-entered transport operations registers."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import ActivityLogRepository, DriverRepository, VehicleRepository
from advancore.services.activity_service import ActivityLogService
from advancore.services.vehicle_service import (
    DuplicateVehicleError,
    VEHICLE_STATUSES,
    VehicleNotFoundError,
    VehicleService,
    VehicleValidationError,
)
from advancore.services.driver_service import (
    DRIVER_STATUSES,
    DriverNotFoundError,
    DriverService,
    DriverValidationError,
    DuplicateDriverReferenceError,
)


@contextmanager
def _vehicle_service() -> Iterator[VehicleService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield VehicleService(
            VehicleRepository(session),
            ActivityLogService(ActivityLogRepository(session)),
        )


@contextmanager
def _driver_service() -> Iterator[DriverService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield DriverService(
            DriverRepository(session),
            ActivityLogService(ActivityLogRepository(session)),
        )


def _create_vehicle(registration: str, make_model: str) -> bool:
    try:
        with _vehicle_service() as service:
            service.create_vehicle(registration, make_model)
    except (VehicleValidationError, DuplicateVehicleError) as exc:
        st.warning(str(exc))
        return False
    except Exception:
        st.error("Vehicle could not be saved. Please try again.")
        return False
    return True


def _change_vehicle_status(vehicle_id: int, status: str) -> bool:
    try:
        with _vehicle_service() as service:
            service.set_status(vehicle_id, status)
    except (VehicleValidationError, VehicleNotFoundError) as exc:
        st.warning(str(exc))
        return False
    except Exception:
        st.error("Vehicle status could not be updated. Please try again.")
        return False
    return True


def _render_vehicle_register() -> None:
    st.subheader("Vehicle register")
    st.caption("Only vehicles you enter are shown. No sample fleet data is generated.")
    with st.form("create_vehicle"):
        registration = st.text_input("Registration number", max_chars=32)
        make_model = st.text_input("Make/model (optional)", max_chars=120)
        submitted = st.form_submit_button("Add vehicle", type="primary")
    if submitted and _create_vehicle(registration, make_model):
        st.success("Vehicle added.")
        st.rerun()

    try:
        with _vehicle_service() as service:
            vehicles = list(service.list_vehicles())
    except Exception:
        st.error("Vehicle register could not be loaded.")
        return
    if not vehicles:
        st.info("No vehicles registered yet.")
        return

    st.dataframe(
        [
            {
                "Registration": vehicle.registration_number,
                "Make/model": vehicle.make_model or "Not provided",
                "Status": vehicle.status.replace("_", " ").title(),
            }
            for vehicle in vehicles
        ],
        use_container_width=True,
        hide_index=True,
    )
    by_id = {vehicle.id: vehicle for vehicle in vehicles}
    with st.form("vehicle_status"):
        vehicle_id = st.selectbox(
            "Vehicle",
            options=list(by_id),
            format_func=lambda identifier: by_id[identifier].registration_number,
        )
        current = by_id[vehicle_id].status
        status = st.selectbox(
            "Status",
            options=list(VEHICLE_STATUSES),
            index=VEHICLE_STATUSES.index(current),
            format_func=lambda value: value.replace("_", " ").title(),
        )
        status_submitted = st.form_submit_button("Update vehicle status")
    if status_submitted and _change_vehicle_status(vehicle_id, status):
        st.success("Vehicle status updated.")
        st.rerun()


def render() -> None:
    st.header("Transport Operations")
    st.write("Build the operational records from real information you enter.")
    _render_vehicle_register()
    st.divider()
    _render_driver_register()


def _render_driver_register() -> None:
    st.subheader("Driver register")
    st.caption("Stores only a name, optional internal reference, and manual status.")
    with st.form("create_driver"):
        name = st.text_input("Driver name", max_chars=120)
        reference = st.text_input("Employee reference (optional)", max_chars=40)
        submitted = st.form_submit_button("Add driver")
    if submitted:
        try:
            with _driver_service() as service: service.create_driver(name, reference)
        except (DriverValidationError, DuplicateDriverReferenceError) as exc: st.warning(str(exc))
        except Exception: st.error("Driver could not be saved. Please try again.")
        else: st.success("Driver added."); st.rerun()
    try:
        with _driver_service() as service: drivers = list(service.list_drivers())
    except Exception: st.error("Driver register could not be loaded."); return
    if not drivers: st.info("No drivers registered yet."); return
    st.dataframe([
        {"Name": item.name, "Employee reference": item.employee_reference or "Not provided", "Status": item.status.title()}
        for item in drivers
    ], use_container_width=True, hide_index=True)
    by_id = {item.id: item for item in drivers}
    with st.form("driver_status"):
        driver_id = st.selectbox("Driver", list(by_id), format_func=lambda key: by_id[key].name)
        current = by_id[driver_id].status
        status = st.selectbox("Driver status", list(DRIVER_STATUSES), index=DRIVER_STATUSES.index(current), format_func=str.title)
        changed = st.form_submit_button("Update driver status")
    if changed:
        try:
            with _driver_service() as service: service.set_status(driver_id, status)
        except (DriverValidationError, DriverNotFoundError) as exc: st.warning(str(exc))
        except Exception: st.error("Driver status could not be updated.")
        else: st.success("Driver status updated."); st.rerun()

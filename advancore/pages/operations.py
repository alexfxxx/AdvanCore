"""Truthful owner-entered transport operations registers."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import ActivityLogRepository, VehicleRepository
from advancore.services.activity_service import ActivityLogService
from advancore.services.vehicle_service import (
    DuplicateVehicleError,
    VEHICLE_STATUSES,
    VehicleNotFoundError,
    VehicleService,
    VehicleValidationError,
)


@contextmanager
def _vehicle_service() -> Iterator[VehicleService]:
    from advancore.services.database import session_scope

    with session_scope() as session:
        yield VehicleService(
            VehicleRepository(session),
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

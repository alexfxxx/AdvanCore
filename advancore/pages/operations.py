"""Truthful owner-entered transport operations screens."""

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from advancore.repositories import (
    ActivityLogRepository,
    CustomerRepository,
    DriverRepository,
    FinancialEntryRepository,
    FuelEntryRepository,
    RouteRepository,
    TripAssignmentRepository,
    TripRepository,
    VehicleRepository,
)
from advancore.services.activity_service import ActivityLogService
from advancore.services.customer_service import (
    CUSTOMER_STATUSES,
    CustomerNotFoundError,
    CustomerService,
    CustomerValidationError,
    DuplicateCustomerReferenceError,
)
from advancore.services.driver_service import (
    DRIVER_STATUSES,
    DriverNotFoundError,
    DriverService,
    DriverValidationError,
    DuplicateDriverReferenceError,
)
from advancore.services.financial_entry_service import (
    FINANCIAL_ENTRY_TYPES,
    FinancialEntryService,
    FinancialEntryValidationError,
)
from advancore.services.fuel_entry_service import FuelEntryService, FuelEntryValidationError
from advancore.services.operational_import_service import (
    DATASET_HEADERS,
    DATASET_LABELS,
    MAX_CSV_BYTES,
    OperationalImportError,
    csv_template,
    preview_csv,
)
from advancore.services.operational_import_review_service import (
    REVIEW_ALREADY_EXISTS,
    REVIEW_DUPLICATE_FILE,
    REVIEW_DUPLICATE_FILE_AND_EXISTS,
    REVIEW_INVALID,
    review_import,
)
from advancore.services.route_service import (
    ROUTE_STATUSES,
    DuplicateRouteError,
    RouteNotFoundError,
    RouteService,
    RouteValidationError,
)
from advancore.services.trip_assignment_service import (
    DuplicateTripAssignmentError,
    TripAssignmentNotFoundError,
    TripAssignmentService,
    TripAssignmentValidationError,
)
from advancore.services.trip_service import (
    TRIP_STATUSES,
    DuplicateTripError,
    TripNotFoundError,
    TripService,
    TripValidationError,
)
from advancore.services.vehicle_service import (
    VEHICLE_STATUSES,
    DuplicateVehicleError,
    VehicleNotFoundError,
    VehicleService,
    VehicleValidationError,
)


def _session_scope():
    from advancore.services.database import session_scope

    return session_scope()


@contextmanager
def _vehicle_service() -> Iterator[VehicleService]:
    with _session_scope() as session:
        yield VehicleService(
            VehicleRepository(session),
            ActivityLogService(ActivityLogRepository(session)),
        )


@contextmanager
def _driver_service() -> Iterator[DriverService]:
    with _session_scope() as session:
        yield DriverService(
            DriverRepository(session),
            ActivityLogService(ActivityLogRepository(session)),
        )


@contextmanager
def _customer_service() -> Iterator[CustomerService]:
    with _session_scope() as session:
        yield CustomerService(
            CustomerRepository(session),
            ActivityLogService(ActivityLogRepository(session)),
        )


@contextmanager
def _route_service() -> Iterator[RouteService]:
    with _session_scope() as session:
        yield RouteService(RouteRepository(session))


@contextmanager
def _trip_service() -> Iterator[TripService]:
    with _session_scope() as session:
        yield TripService(TripRepository(session))


@contextmanager
def _assignment_service() -> Iterator[TripAssignmentService]:
    with _session_scope() as session:
        yield TripAssignmentService(TripAssignmentRepository(session))


@contextmanager
def _fuel_service() -> Iterator[FuelEntryService]:
    with _session_scope() as session:
        yield FuelEntryService(FuelEntryRepository(session))


@contextmanager
def _financial_service() -> Iterator[FinancialEntryService]:
    with _session_scope() as session:
        yield FinancialEntryService(FinancialEntryRepository(session))


def _load(service_scope, method: str, error_message: str):
    try:
        with service_scope() as service:
            return list(getattr(service, method)())
    except Exception:
        st.error(error_message)
        return None


def _existing_import_identities(dataset_type: str) -> set[str] | None:
    configuration = {
        "vehicles": (_vehicle_service, "list_vehicles", "registration_number"),
        "drivers": (_driver_service, "list_drivers", "employee_reference"),
        "customers": (_customer_service, "list_customers", "customer_reference"),
        "routes": (_route_service, "list_routes", "route_code"),
    }
    service_scope, method, attribute = configuration[dataset_type]
    records = _load(
        service_scope,
        method,
        f"{DATASET_LABELS[dataset_type]} could not be loaded for duplicate review.",
    )
    if records is None:
        return None
    return {
        value
        for record in records
        if isinstance((value := getattr(record, attribute, None)), str) and value
    }


def _render_setup() -> None:
    st.subheader("Operational CSV setup")
    st.caption(
        "Preview only: uploaded rows stay in memory and are never saved to the database."
    )
    dataset_type = st.selectbox(
        "CSV dataset",
        list(DATASET_HEADERS),
        format_func=lambda value: DATASET_LABELS[value],
    )
    st.download_button(
        f"Download {DATASET_LABELS[dataset_type].lower()} template",
        data=csv_template(dataset_type),
        file_name=f"advancore_{dataset_type}_template.csv",
        mime="text/csv",
        key=f"download_{dataset_type}_template",
    )
    upload = st.file_uploader(
        f"Upload completed {DATASET_LABELS[dataset_type].lower()} CSV",
        type=["csv"],
        key=f"upload_{dataset_type}_csv",
        max_upload_size=1,
    )
    if upload is None:
        st.info("Download a template, complete it locally, then upload it for validation.")
        return
    reported_size = getattr(upload, "size", None)
    if reported_size is not None and reported_size > MAX_CSV_BYTES:
        st.warning("CSV file exceeds the 1 MiB preview limit.")
        return
    try:
        preview = preview_csv(dataset_type, upload.getvalue())
    except OperationalImportError as exc:
        st.warning(str(exc))
        return

    st.write(
        f"Previewed {len(preview.rows):,} row(s): "
        f"{preview.valid_row_count:,} valid and {preview.invalid_row_count:,} requiring correction."
    )
    if not preview.rows:
        st.info("The template contains no data rows to preview.")
        return
    st.dataframe(
        [
            {
                "CSV row": row.row_number,
                "Status": "Valid" if row.is_valid else "Needs correction",
                **{header: row.values[header] or "" for header in preview.headers},
                "Validation": "; ".join(row.errors) if row.errors else "Ready for later review",
            }
            for row in preview.rows
        ],
        use_container_width=True,
        hide_index=True,
    )
    if preview.invalid_row_count:
        st.warning("Correct every invalid row before a later governed import review.")
    else:
        st.success("All rows pass preview validation. Nothing has been saved.")

    existing_identities = _existing_import_identities(dataset_type)
    if existing_identities is None:
        return
    review = review_import(preview, existing_identities)
    st.subheader("Import review queue")
    st.caption(
        "Read-only exact duplicate review. No records are created from this screen."
    )
    existing_count = review.count(REVIEW_ALREADY_EXISTS) + review.count(
        REVIEW_DUPLICATE_FILE_AND_EXISTS
    )
    file_duplicate_count = review.count(REVIEW_DUPLICATE_FILE) + review.count(
        REVIEW_DUPLICATE_FILE_AND_EXISTS
    )
    st.write(
        f"{review.publishable_count:,} ready; "
        f"{existing_count:,} already exist; "
        f"{file_duplicate_count:,} duplicated in file; "
        f"{review.count(REVIEW_INVALID):,} invalid."
    )
    st.dataframe(
        [
            {
                "CSV row": item.preview_row.row_number,
                "Review status": item.status.replace("_", " ").title(),
                "Review": item.message,
            }
            for item in review.rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_vehicle_register() -> None:
    st.subheader("Vehicle register")
    st.caption("Only vehicles you enter are shown. No sample fleet data is generated.")
    with st.form("create_vehicle"):
        registration = st.text_input("Registration number", max_chars=32)
        make_model = st.text_input("Make/model (optional)", max_chars=120)
        submitted = st.form_submit_button("Add vehicle", type="primary")
    if submitted:
        try:
            with _vehicle_service() as service:
                service.create_vehicle(registration, make_model)
        except (VehicleValidationError, DuplicateVehicleError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Vehicle could not be saved. Please try again.")
        else:
            st.success("Vehicle added.")
            st.rerun()

    vehicles = _load(_vehicle_service, "list_vehicles", "Vehicle register could not be loaded.")
    if vehicles is None:
        return
    if not vehicles:
        st.info("No vehicles registered yet.")
        return
    st.dataframe(
        [
            {
                "Registration": item.registration_number,
                "Make/model": item.make_model or "Not provided",
                "Status": item.status.replace("_", " ").title(),
            }
            for item in vehicles
        ],
        use_container_width=True,
        hide_index=True,
    )
    by_id = {item.id: item for item in vehicles}
    with st.form("vehicle_status"):
        identifier = st.selectbox("Vehicle", list(by_id), format_func=lambda key: by_id[key].registration_number)
        current = by_id[identifier].status
        status = st.selectbox(
            "Vehicle status",
            list(VEHICLE_STATUSES),
            index=VEHICLE_STATUSES.index(current),
            format_func=lambda value: value.replace("_", " ").title(),
        )
        changed = st.form_submit_button("Update vehicle status")
    if changed:
        try:
            with _vehicle_service() as service:
                service.set_status(identifier, status)
        except (VehicleValidationError, VehicleNotFoundError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Vehicle status could not be updated.")
        else:
            st.success("Vehicle status updated.")
            st.rerun()


def _render_driver_register() -> None:
    st.subheader("Driver register")
    st.caption("Stores only a name, optional internal reference, and manual status.")
    with st.form("create_driver"):
        name = st.text_input("Driver name", max_chars=120)
        reference = st.text_input("Employee reference (optional)", max_chars=40)
        submitted = st.form_submit_button("Add driver")
    if submitted:
        try:
            with _driver_service() as service:
                service.create_driver(name, reference)
        except (DriverValidationError, DuplicateDriverReferenceError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Driver could not be saved. Please try again.")
        else:
            st.success("Driver added.")
            st.rerun()
    drivers = _load(_driver_service, "list_drivers", "Driver register could not be loaded.")
    if drivers is None:
        return
    if not drivers:
        st.info("No drivers registered yet.")
        return
    st.dataframe(
        [
            {
                "Name": item.name,
                "Employee reference": item.employee_reference or "Not provided",
                "Status": item.status.title(),
            }
            for item in drivers
        ],
        use_container_width=True,
        hide_index=True,
    )
    by_id = {item.id: item for item in drivers}
    with st.form("driver_status"):
        identifier = st.selectbox("Driver", list(by_id), format_func=lambda key: by_id[key].name)
        current = by_id[identifier].status
        status = st.selectbox("Driver status", list(DRIVER_STATUSES), index=DRIVER_STATUSES.index(current), format_func=str.title)
        changed = st.form_submit_button("Update driver status")
    if changed:
        try:
            with _driver_service() as service:
                service.set_status(identifier, status)
        except (DriverValidationError, DriverNotFoundError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Driver status could not be updated.")
        else:
            st.success("Driver status updated.")
            st.rerun()


def _render_customer_register() -> None:
    st.subheader("Customer register")
    st.caption("Stores only a business/customer name, optional internal reference, and status.")
    with st.form("create_customer"):
        name = st.text_input("Customer name", max_chars=160)
        reference = st.text_input("Customer reference (optional)", max_chars=40)
        submitted = st.form_submit_button("Add customer")
    if submitted:
        try:
            with _customer_service() as service:
                service.create_customer(name, reference)
        except (CustomerValidationError, DuplicateCustomerReferenceError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Customer could not be saved.")
        else:
            st.success("Customer added.")
            st.rerun()
    customers = _load(_customer_service, "list_customers", "Customer register could not be loaded.")
    if customers is None:
        return
    if not customers:
        st.info("No customers registered yet.")
        return
    st.dataframe(
        [
            {
                "Customer": item.name,
                "Reference": item.customer_reference or "Not provided",
                "Status": item.status.title(),
            }
            for item in customers
        ],
        use_container_width=True,
        hide_index=True,
    )
    by_id = {item.id: item for item in customers}
    with st.form("customer_status"):
        identifier = st.selectbox("Customer", list(by_id), format_func=lambda key: by_id[key].name)
        current = by_id[identifier].status
        status = st.selectbox("Customer status", list(CUSTOMER_STATUSES), index=CUSTOMER_STATUSES.index(current), format_func=str.title)
        changed = st.form_submit_button("Update customer status")
    if changed:
        try:
            with _customer_service() as service:
                service.set_status(identifier, status)
        except (CustomerValidationError, CustomerNotFoundError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Customer status could not be updated.")
        else:
            st.success("Customer status updated.")
            st.rerun()


def _render_route_register() -> None:
    st.subheader("Route register")
    st.caption("Routes are explicit origin-to-destination records. No distance or timing is inferred.")
    with st.form("create_route"):
        code = st.text_input("Route code", max_chars=40)
        origin = st.text_input("Origin", max_chars=160)
        destination = st.text_input("Destination", max_chars=160)
        submitted = st.form_submit_button("Add route")
    if submitted:
        try:
            with _route_service() as service:
                service.create_route(code, origin, destination)
        except (RouteValidationError, DuplicateRouteError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Route could not be saved.")
        else:
            st.success("Route added.")
            st.rerun()
    routes = _load(_route_service, "list_routes", "Route register could not be loaded.")
    if routes is None:
        return
    if not routes:
        st.info("No routes registered yet.")
        return
    st.dataframe(
        [
            {"Code": item.route_code, "Origin": item.origin, "Destination": item.destination, "Status": item.status.title()}
            for item in routes
        ],
        use_container_width=True,
        hide_index=True,
    )
    by_id = {item.id: item for item in routes}
    with st.form("route_status"):
        identifier = st.selectbox("Route", list(by_id), format_func=lambda key: by_id[key].route_code)
        current = by_id[identifier].status
        status = st.selectbox("Route status", list(ROUTE_STATUSES), index=ROUTE_STATUSES.index(current), format_func=str.title)
        changed = st.form_submit_button("Update route status")
    if changed:
        try:
            with _route_service() as service:
                service.set_status(identifier, status)
        except (RouteValidationError, RouteNotFoundError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Route status could not be updated.")
        else:
            st.success("Route status updated.")
            st.rerun()


def _render_trip_register() -> None:
    st.subheader("Daily trip planning")
    routes = _load(_route_service, "list_routes", "Routes could not be loaded.")
    if routes is None:
        return
    route_by_id = {item.id: item for item in routes}
    if route_by_id:
        with st.form("create_trip"):
            reference = st.text_input("Trip reference", max_chars=40)
            route_id = st.selectbox(
                "Trip route",
                list(route_by_id),
                format_func=lambda key: f"{route_by_id[key].route_code}: {route_by_id[key].origin} → {route_by_id[key].destination}",
            )
            service_date = st.date_input("Service date")
            submitted = st.form_submit_button("Plan trip")
        if submitted:
            try:
                with _trip_service() as service:
                    service.create_trip(reference, route_id, service_date)
            except (TripValidationError, DuplicateTripError) as exc:
                st.warning(str(exc))
            except Exception:
                st.error("Trip could not be saved.")
            else:
                st.success("Trip planned.")
                st.rerun()
    else:
        st.info("Add a route before planning a trip.")
    trips = _load(_trip_service, "list_trips", "Trips could not be loaded.")
    if trips is None:
        return
    if not trips:
        st.info("No trips planned yet.")
        return
    st.dataframe(
        [
            {
                "Reference": item.trip_reference,
                "Route": route_by_id[item.route_id].route_code if item.route_id in route_by_id else f"Route #{item.route_id}",
                "Service date": item.service_date.isoformat(),
                "Status": item.status.title(),
            }
            for item in trips
        ],
        use_container_width=True,
        hide_index=True,
    )
    by_id = {item.id: item for item in trips}
    with st.form("trip_status"):
        identifier = st.selectbox("Trip", list(by_id), format_func=lambda key: by_id[key].trip_reference)
        current = by_id[identifier].status
        status = st.selectbox("Trip status", list(TRIP_STATUSES), index=TRIP_STATUSES.index(current), format_func=str.title)
        changed = st.form_submit_button("Update trip status")
    if changed:
        try:
            with _trip_service() as service:
                service.set_status(identifier, status)
        except (TripValidationError, TripNotFoundError) as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Trip status could not be updated.")
        else:
            st.success("Trip status updated.")
            st.rerun()


def _render_assignments() -> None:
    st.subheader("Trip assignments")
    trips = _load(_trip_service, "list_trips", "Trips could not be loaded.")
    vehicles = _load(_vehicle_service, "list_vehicles", "Vehicles could not be loaded.")
    drivers = _load(_driver_service, "list_drivers", "Drivers could not be loaded.")
    assignments = _load(_assignment_service, "list_assignments", "Assignments could not be loaded.")
    if any(items is None for items in (trips, vehicles, drivers, assignments)):
        return
    trip_by_id = {item.id: item for item in trips}
    vehicle_by_id = {item.id: item for item in vehicles}
    driver_by_id = {item.id: item for item in drivers}
    assigned_trip_ids = {item.trip_id for item in assignments}
    all_planned = {key: item for key, item in trip_by_id.items() if item.status == "planned"}
    planned = {
        key: item
        for key, item in all_planned.items()
        if key not in assigned_trip_ids
    }
    active_vehicles = {key: item for key, item in vehicle_by_id.items() if item.status == "active"}
    active_drivers = {key: item for key, item in driver_by_id.items() if item.status == "active"}
    if planned and active_vehicles and active_drivers:
        with st.form("create_assignment"):
            trip_id = st.selectbox("Assignment trip", list(planned), format_func=lambda key: planned[key].trip_reference)
            vehicle_id = st.selectbox("Assignment vehicle", list(active_vehicles), format_func=lambda key: active_vehicles[key].registration_number)
            driver_id = st.selectbox("Assignment driver", list(active_drivers), format_func=lambda key: active_drivers[key].name)
            submitted = st.form_submit_button("Assign trip")
        if submitted:
            try:
                with _assignment_service() as service:
                    service.assign(trip_id, vehicle_id, driver_id)
            except (TripAssignmentValidationError, DuplicateTripAssignmentError) as exc:
                st.warning(str(exc))
            except Exception:
                st.error("Assignment could not be saved.")
            else:
                st.success("Trip assigned.")
                st.rerun()
    elif not all_planned:
        st.info("Plan a trip before creating an assignment.")
    elif not planned:
        st.info("Every planned trip already has an assignment record. Existing assignment records cannot be replaced.")
    elif not active_vehicles:
        st.info("Set at least one vehicle to Active before creating an assignment.")
    else:
        st.info("Set at least one driver to Active before creating an assignment.")
    if not assignments:
        st.info("No trip assignments recorded yet.")
        return
    st.dataframe(
        [
            {
                "Trip": trip_by_id[item.trip_id].trip_reference if item.trip_id in trip_by_id else f"Trip #{item.trip_id}",
                "Vehicle": vehicle_by_id[item.vehicle_id].registration_number if item.vehicle_id in vehicle_by_id else f"Vehicle #{item.vehicle_id}",
                "Driver": driver_by_id[item.driver_id].name if item.driver_id in driver_by_id else f"Driver #{item.driver_id}",
                "Status": item.status.title(),
            }
            for item in assignments
        ],
        use_container_width=True,
        hide_index=True,
    )
    assigned = {item.id: item for item in assignments if item.status == "assigned"}
    if assigned:
        with st.form("release_assignment"):
            identifier = st.selectbox(
                "Active assignment",
                list(assigned),
                format_func=lambda key: trip_by_id[assigned[key].trip_id].trip_reference
                if assigned[key].trip_id in trip_by_id
                else f"Assignment #{key}",
            )
            released = st.form_submit_button("Release assignment")
        if released:
            try:
                with _assignment_service() as service:
                    service.release(identifier)
            except (TripAssignmentValidationError, TripAssignmentNotFoundError) as exc:
                st.warning(str(exc))
            except Exception:
                st.error("Assignment could not be released.")
            else:
                st.success("Assignment released.")
                st.rerun()


def _render_fuel_entries() -> None:
    st.subheader("Fuel records")
    st.caption("Fuel records are immutable. Corrections require a new entry and an explanatory business process.")
    vehicles = _load(_vehicle_service, "list_vehicles", "Vehicles could not be loaded.")
    if vehicles is None:
        return
    vehicle_by_id = {item.id: item for item in vehicles}
    if vehicle_by_id:
        with st.form("create_fuel_entry"):
            vehicle_id = st.selectbox("Fuel vehicle", list(vehicle_by_id), format_func=lambda key: vehicle_by_id[key].registration_number)
            recorded_on = st.date_input("Fuel date")
            litres = st.number_input("Litres", min_value=0.0, step=0.01, format="%.2f")
            has_total_cost = st.checkbox("Include total cost")
            total_cost = (
                st.number_input("Total cost", min_value=0.0, step=0.01, format="%.2f")
                if has_total_cost
                else None
            )
            has_odometer = st.checkbox("Include odometer reading")
            odometer = (
                st.number_input("Odometer km", min_value=0.0, step=0.1, format="%.1f")
                if has_odometer
                else None
            )
            submitted = st.form_submit_button("Record fuel")
        if submitted:
            try:
                with _fuel_service() as service:
                    service.record(vehicle_id, recorded_on, litres, total_cost, odometer)
            except FuelEntryValidationError as exc:
                st.warning(str(exc))
            except Exception:
                st.error("Fuel entry could not be saved.")
            else:
                st.success("Fuel entry recorded.")
                st.rerun()
    else:
        st.info("Add a vehicle before recording fuel.")
    entries = _load(_fuel_service, "list_entries", "Fuel entries could not be loaded.")
    if entries is None:
        return
    if not entries:
        st.info("No fuel entries recorded yet.")
        return
    st.dataframe(
        [
            {
                "Date": item.recorded_on.isoformat(),
                "Vehicle": vehicle_by_id[item.vehicle_id].registration_number if item.vehicle_id in vehicle_by_id else f"Vehicle #{item.vehicle_id}",
                "Litres": str(item.litres),
                "Total cost": str(item.total_cost) if item.total_cost is not None else "Not provided",
                "Odometer km": str(item.odometer_km) if item.odometer_km is not None else "Not provided",
            }
            for item in entries
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_financial_entries() -> None:
    st.subheader("Financial records")
    st.caption("Owner-entered immutable facts only. AdvanCore does not invent revenue, cost, or profitability figures.")
    trips = _load(_trip_service, "list_trips", "Trips could not be loaded.")
    customers = _load(_customer_service, "list_customers", "Customers could not be loaded.")
    if trips is None or customers is None:
        return
    trip_by_id = {item.id: item for item in trips}
    customer_by_id = {item.id: item for item in customers}
    with st.form("create_financial_entry"):
        entry_date = st.date_input("Entry date")
        entry_type = st.selectbox("Entry type", list(FINANCIAL_ENTRY_TYPES), format_func=str.title)
        amount = st.number_input("Amount", min_value=0.0, step=0.01, format="%.2f")
        currency = st.text_input("Currency code", value="SGD", max_chars=3)
        description = st.text_input("Description (optional)", max_chars=200)
        trip_id = st.selectbox(
            "Related trip (optional)",
            [None, *trip_by_id],
            format_func=lambda key: "None" if key is None else trip_by_id[key].trip_reference,
        )
        customer_id = st.selectbox(
            "Related customer (optional)",
            [None, *customer_by_id],
            format_func=lambda key: "None" if key is None else customer_by_id[key].name,
        )
        submitted = st.form_submit_button("Record financial entry")
    if submitted:
        try:
            with _financial_service() as service:
                service.record(entry_date, entry_type, amount, currency, description, trip_id, customer_id)
        except FinancialEntryValidationError as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Financial entry could not be saved.")
        else:
            st.success("Financial entry recorded.")
            st.rerun()
    entries = _load(_financial_service, "list_entries", "Financial entries could not be loaded.")
    if entries is None:
        return
    if not entries:
        st.info("No financial entries recorded yet.")
        return
    st.dataframe(
        [
            {
                "Date": item.entry_date.isoformat(),
                "Type": item.entry_type.title(),
                "Amount": str(item.amount),
                "Currency": item.currency_code,
                "Description": item.description or "Not provided",
                "Trip": trip_by_id[item.trip_id].trip_reference
                if item.trip_id in trip_by_id
                else ("None" if item.trip_id is None else f"Trip #{item.trip_id}"),
                "Customer": customer_by_id[item.customer_id].name
                if item.customer_id in customer_by_id
                else ("None" if item.customer_id is None else f"Customer #{item.customer_id}"),
            }
            for item in entries
        ],
        use_container_width=True,
        hide_index=True,
    )


def render() -> None:
    st.header("Transport Operations")
    st.write("Build operational records from real information you enter. AdvanCore does not generate sample business data.")
    tabs = st.tabs(["Setup", "Fleet", "Drivers", "Customers", "Routes", "Trips", "Assignments", "Fuel", "Finance"])
    renderers = (
        _render_setup,
        _render_vehicle_register,
        _render_driver_register,
        _render_customer_register,
        _render_route_register,
        _render_trip_register,
        _render_assignments,
        _render_fuel_entries,
        _render_financial_entries,
    )
    for tab, renderer in zip(tabs, renderers, strict=True):
        with tab:
            renderer()

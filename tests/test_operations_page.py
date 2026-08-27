from contextlib import contextmanager, nullcontext
from datetime import date
from types import SimpleNamespace

from advancore.pages import operations


class FakeStreamlit:
    def __init__(self, submitted_label=None, inputs=None):
        self.messages = []
        self.dataframes = []
        self.submitted_label = submitted_label
        self.inputs = inputs or {}
        self.rerun_calls = 0
        self.downloads = []

    def _record(self, kind, value): self.messages.append((kind, str(value)))
    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def caption(self, value): self._record("caption", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def success(self, value): self._record("success", value)
    def text_input(self, label, **kwargs): return self.inputs.get(label, kwargs.get("value", ""))
    def date_input(self, label, **_kwargs): return self.inputs.get(label, date(2026, 8, 27))
    def number_input(self, label, **_kwargs): return self.inputs.get(label, 0.0)
    def checkbox(self, label, **_kwargs): return self.inputs.get(label, False)
    def button(self, label, **_kwargs): return label == self.submitted_label
    def selectbox(self, label, options, **_kwargs): return self.inputs.get(label, options[0])
    def form_submit_button(self, label, **_kwargs): return label == self.submitted_label
    def rerun(self): self.rerun_calls += 1
    def dataframe(self, rows, **_kwargs): self.dataframes.append(rows)
    def download_button(self, label, **kwargs): self.downloads.append((label, kwargs))
    def file_uploader(self, label, **_kwargs): return self.inputs.get(label)

    def tabs(self, labels):
        self._record("tabs", "|".join(labels))
        return [nullcontext() for _ in labels]

    @contextmanager
    def form(self, _key):
        yield

    def text(self):
        return "\n".join(message for _, message in self.messages)


class EmptyService:
    def __getattr__(self, name):
        if name.startswith("list_"):
            return lambda: []
        raise AttributeError(name)


def scope_for(service):
    @contextmanager
    def scope():
        yield service

    return scope


def install_empty_services(monkeypatch):
    for name in (
        "_vehicle_service", "_driver_service", "_customer_service", "_route_service",
        "_trip_service", "_assignment_service", "_fuel_service", "_financial_service",
    ):
        monkeypatch.setattr(operations, name, scope_for(EmptyService()))


def test_transport_operations_starts_truthfully_empty(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(operations, "st", fake_st)
    install_empty_services(monkeypatch)

    operations.render()

    text = fake_st.text()
    assert "Transport Operations" in text
    assert "Setup|Dispatch|Fleet|Drivers|Customers|Routes|Trips|Assignments|Fuel|Finance" in text
    assert "No vehicles registered yet" in text
    assert "No routes registered yet" in text
    assert "No trips planned yet" in text
    assert "No trip assignments recorded yet" in text
    assert "No fuel entries recorded yet" in text
    assert "No financial entries recorded yet" in text
    assert "No trips are recorded for the selected dispatch date" in text
    assert "does not generate sample business data" in text
    assert fake_st.dataframes == []
    assert fake_st.downloads[0][1]["data"] == b"registration_number,make_model\n"


def test_setup_previews_uploaded_rows_without_using_database(monkeypatch):
    upload = SimpleNamespace(getvalue=lambda: b"name,employee_reference\n Alex Tan , drv-7 \n")
    fake_st = FakeStreamlit(
        inputs={
            "CSV dataset": "drivers",
            "Upload completed drivers CSV": upload,
        }
    )
    monkeypatch.setattr(operations, "st", fake_st)
    monkeypatch.setattr(operations, "_driver_service", scope_for(EmptyService()))

    operations._render_setup()

    assert "Previewed 1 row(s): 1 valid and 0 requiring correction" in fake_st.text()
    assert "Nothing has been saved" in fake_st.text()
    assert fake_st.dataframes[0] == [{
        "CSV row": 2,
        "Status": "Valid",
        "name": "Alex Tan",
        "employee_reference": "DRV-7",
        "Validation": "Ready for later review",
    }]
    assert fake_st.dataframes[1][0]["Review status"] == "Ready"
    assert "1 ready; 0 already exist" in fake_st.text()


def test_setup_flags_exact_database_duplicate(monkeypatch):
    upload = SimpleNamespace(
        getvalue=lambda: b"registration_number,make_model\nBUS-1,Model\n"
    )
    fake_st = FakeStreamlit(inputs={"Upload completed vehicles CSV": upload})
    existing = SimpleNamespace(registration_number="BUS-1")
    service = EmptyService()
    service.list_vehicles = lambda: [existing]
    monkeypatch.setattr(operations, "st", fake_st)
    monkeypatch.setattr(operations, "_vehicle_service", scope_for(service))

    operations._render_setup()

    assert fake_st.dataframes[1][0]["Review status"] == "Already Exists"
    assert "0 ready; 1 already exist" in fake_st.text()


def test_setup_publishes_fully_ready_confirmed_batch_through_service(monkeypatch):
    upload = SimpleNamespace(
        getvalue=lambda: b"registration_number,make_model\nTEST-1,Model\n"
    )
    confirmation = "I reviewed all 1 row(s) and approve creating these records."
    fake_st = FakeStreamlit(
        submitted_label="Publish 1 vehicles record(s)",
        inputs={
            "Upload completed vehicles CSV": upload,
            confirmation: True,
        },
    )
    service = EmptyService()
    service.list_vehicles = lambda: []
    service.calls = []
    service.create_vehicle = lambda *values: service.calls.append(values)
    monkeypatch.setattr(operations, "st", fake_st)
    monkeypatch.setattr(operations, "_vehicle_service", scope_for(service))

    operations._render_setup()

    assert service.calls == [("TEST-1", "Model")]
    assert "Published 1 record(s)" in fake_st.text()
    assert fake_st.rerun_calls == 1


def test_setup_rejects_reported_oversized_upload_before_reading(monkeypatch):
    def unexpected_read():
        raise AssertionError("oversized upload must not be materialized")

    upload = SimpleNamespace(size=1_048_577, getvalue=unexpected_read)
    fake_st = FakeStreamlit(inputs={"Upload completed vehicles CSV": upload})
    monkeypatch.setattr(operations, "st", fake_st)

    operations._render_setup()

    assert "exceeds the 1 MiB preview limit" in fake_st.text()
    assert fake_st.dataframes == []


def test_route_form_calls_route_service(monkeypatch):
    service = EmptyService()
    service.calls = []
    service.create_route = lambda *args: service.calls.append(args)
    service.list_routes = lambda: []
    fake_st = FakeStreamlit(
        submitted_label="Add route",
        inputs={"Route code": "r1", "Origin": "Depot", "Destination": "Terminal"},
    )
    monkeypatch.setattr(operations, "st", fake_st)
    monkeypatch.setattr(operations, "_route_service", scope_for(service))

    operations._render_route_register()

    assert service.calls == [("r1", "Depot", "Terminal")]
    assert fake_st.rerun_calls == 1


def test_dispatch_board_renders_recorded_daily_state(monkeypatch):
    route = SimpleNamespace(id=1, route_code="R1", origin="North", destination="South")
    trip = SimpleNamespace(
        id=2,
        trip_reference="T1",
        route_id=1,
        service_date=date(2026, 8, 27),
        status="planned",
    )
    vehicle = SimpleNamespace(id=3, registration_number="BUS-1", status="active")
    available_vehicle = SimpleNamespace(id=5, registration_number="BUS-2", status="active")
    driver = SimpleNamespace(id=4, name="Driver One", status="active")
    available_driver = SimpleNamespace(id=6, name="Driver Two", status="active")
    assignment = SimpleNamespace(
        trip_id=2,
        vehicle_id=3,
        driver_id=4,
        status="assigned",
    )

    def listed(method, rows):
        service = EmptyService()
        setattr(service, method, lambda: rows)
        return service

    monkeypatch.setattr(operations, "_route_service", scope_for(listed("list_routes", [route])))
    monkeypatch.setattr(operations, "_trip_service", scope_for(listed("list_trips", [trip])))
    monkeypatch.setattr(
        operations,
        "_vehicle_service",
        scope_for(listed("list_vehicles", [vehicle, available_vehicle])),
    )
    monkeypatch.setattr(
        operations,
        "_driver_service",
        scope_for(listed("list_drivers", [driver, available_driver])),
    )
    monkeypatch.setattr(
        operations,
        "_assignment_service",
        scope_for(listed("list_assignments", [assignment])),
    )
    fake_st = FakeStreamlit()
    monkeypatch.setattr(operations, "st", fake_st)

    operations._render_dispatch_board()

    assert "1 trip(s): 1 assigned, 0 unassigned" in fake_st.text()
    assert fake_st.dataframes[0][0]["Route"] == "R1: North → South"
    assert fake_st.dataframes[0][0]["Vehicle"] == "BUS-1"
    assert "Available active vehicles: BUS-2" in fake_st.text()
    assert "Available active drivers: Driver Two" in fake_st.text()


def test_trip_assignment_fuel_and_finance_forms_use_services(monkeypatch):
    route = SimpleNamespace(id=1, route_code="R1", origin="Depot", destination="Terminal", status="active")
    trip = SimpleNamespace(id=2, trip_reference="T1", route_id=1, service_date=date(2026, 8, 27), status="planned")
    vehicle = SimpleNamespace(id=3, registration_number="BUS-1", make_model=None, status="active")
    driver = SimpleNamespace(id=4, name="Alex", employee_reference=None, status="active")
    customer = SimpleNamespace(id=5, name="Acme", customer_reference=None, status="active")

    def make_service(list_name, rows, method_name):
        service = EmptyService()
        setattr(service, list_name, lambda: rows)
        service.calls = []
        setattr(service, method_name, lambda *args: service.calls.append(args))
        return service

    route_service = make_service("list_routes", [route], "unused")
    trip_service = make_service("list_trips", [trip], "create_trip")
    vehicle_service = make_service("list_vehicles", [vehicle], "unused_vehicle")
    driver_service = make_service("list_drivers", [driver], "unused_driver")
    customer_service = make_service("list_customers", [customer], "unused_customer")
    assignment_service = make_service("list_assignments", [], "assign")
    fuel_service = make_service("list_entries", [], "record")
    financial_service = make_service("list_entries", [], "record")

    monkeypatch.setattr(operations, "_route_service", scope_for(route_service))
    monkeypatch.setattr(operations, "_trip_service", scope_for(trip_service))
    monkeypatch.setattr(operations, "_vehicle_service", scope_for(vehicle_service))
    monkeypatch.setattr(operations, "_driver_service", scope_for(driver_service))
    monkeypatch.setattr(operations, "_customer_service", scope_for(customer_service))
    monkeypatch.setattr(operations, "_assignment_service", scope_for(assignment_service))
    monkeypatch.setattr(operations, "_fuel_service", scope_for(fuel_service))
    monkeypatch.setattr(operations, "_financial_service", scope_for(financial_service))

    monkeypatch.setattr(operations, "st", FakeStreamlit(submitted_label="Plan trip", inputs={"Trip reference": "T1"}))
    operations._render_trip_register()
    assert trip_service.calls == [("T1", 1, date(2026, 8, 27))]

    monkeypatch.setattr(operations, "st", FakeStreamlit(submitted_label="Assign trip"))
    operations._render_assignments()
    assert assignment_service.calls == [(2, 3, 4)]

    monkeypatch.setattr(operations, "st", FakeStreamlit(submitted_label="Record fuel", inputs={"Litres": 25.5}))
    operations._render_fuel_entries()
    assert fuel_service.calls == [(3, date(2026, 8, 27), 25.5, None, None)]

    monkeypatch.setattr(operations, "st", FakeStreamlit(submitted_label="Record financial entry", inputs={"Amount": 100.0}))
    operations._render_financial_entries()
    assert financial_service.calls == [(date(2026, 8, 27), "income", 100.0, "SGD", "", None, None)]


def test_existing_assignment_trip_is_not_offered_again(monkeypatch):
    trip = SimpleNamespace(id=2, trip_reference="T1", status="planned")
    vehicle = SimpleNamespace(id=3, registration_number="BUS-1", status="active")
    driver = SimpleNamespace(id=4, name="Alex", status="active")
    assignment = SimpleNamespace(id=6, trip_id=2, vehicle_id=3, driver_id=4, status="released")

    def listed(method, rows):
        service = EmptyService()
        setattr(service, method, lambda: rows)
        return service

    monkeypatch.setattr(operations, "_trip_service", scope_for(listed("list_trips", [trip])))
    monkeypatch.setattr(operations, "_vehicle_service", scope_for(listed("list_vehicles", [vehicle])))
    monkeypatch.setattr(operations, "_driver_service", scope_for(listed("list_drivers", [driver])))
    monkeypatch.setattr(operations, "_assignment_service", scope_for(listed("list_assignments", [assignment])))
    fake_st = FakeStreamlit(submitted_label="Assign trip")
    monkeypatch.setattr(operations, "st", fake_st)

    operations._render_assignments()

    assert "Every planned trip already has an assignment record" in fake_st.text()
    assert fake_st.rerun_calls == 0

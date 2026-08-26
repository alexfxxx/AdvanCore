from contextlib import contextmanager
from types import SimpleNamespace

from advancore.pages import operations


class FakeStreamlit:
    def __init__(self, submitted_label=None):
        self.messages = []
        self.rows = None
        self.submitted_label = submitted_label
        self.rerun_calls = 0

    def _record(self, kind, value):
        self.messages.append((kind, str(value)))

    def header(self, value): self._record("header", value)
    def subheader(self, value): self._record("subheader", value)
    def write(self, value): self._record("write", value)
    def caption(self, value): self._record("caption", value)
    def info(self, value): self._record("info", value)
    def warning(self, value): self._record("warning", value)
    def error(self, value): self._record("error", value)
    def success(self, value): self._record("success", value)
    def text_input(self, _label, **_kwargs): return ""
    def form_submit_button(self, label, **_kwargs): return label == self.submitted_label
    def rerun(self): self.rerun_calls += 1
    def dataframe(self, rows, **_kwargs): self.rows = rows
    def divider(self): pass
    def selectbox(self, _label, options, **_kwargs): return options[0]

    @contextmanager
    def form(self, _key):
        yield

    def text(self):
        return "\n".join(message for _, message in self.messages)


class EmptyVehicleService:
    def list_vehicles(self):
        return []

class EmptyDriverService:
    def list_drivers(self): return []
class EmptyCustomerService:
    def list_customers(self): return []


def test_transport_operations_starts_truthfully_empty(monkeypatch):
    fake_st = FakeStreamlit()

    @contextmanager
    def service_scope():
        yield EmptyVehicleService()

    monkeypatch.setattr(operations, "st", fake_st)
    monkeypatch.setattr(operations, "_vehicle_service", service_scope)
    @contextmanager
    def driver_scope(): yield EmptyDriverService()
    monkeypatch.setattr(operations, "_driver_service", driver_scope)
    @contextmanager
    def customer_scope(): yield EmptyCustomerService()
    monkeypatch.setattr(operations, "_customer_service", customer_scope)

    operations.render()

    assert "Transport Operations" in fake_st.text()
    assert "No vehicles registered yet" in fake_st.text()
    assert "No drivers registered yet" in fake_st.text()
    assert "No customers registered yet" in fake_st.text()
    assert "sample fleet data" in fake_st.text()
    assert fake_st.rows is None


def test_customer_status_can_be_changed_from_operations_page(monkeypatch):
    service = EmptyCustomerService()
    service.calls = []
    service.list_customers = lambda: [
        SimpleNamespace(id=7, name="Customer", customer_reference=None, status="active")
    ]
    service.set_status = lambda identifier, status: service.calls.append((identifier, status))
    fake_st = FakeStreamlit(submitted_label="Update customer status")

    @contextmanager
    def customer_scope(): yield service
    monkeypatch.setattr(operations, "st", fake_st)
    monkeypatch.setattr(operations, "_customer_service", customer_scope)

    operations._render_customer_register()

    assert service.calls == [(7, "active")]
    assert fake_st.rerun_calls == 1

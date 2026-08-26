from contextlib import contextmanager

from advancore.pages import operations


class FakeStreamlit:
    def __init__(self):
        self.messages = []
        self.rows = None

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
    def form_submit_button(self, _label, **_kwargs): return False
    def rerun(self): raise AssertionError("empty render must not rerun")
    def dataframe(self, rows, **_kwargs): self.rows = rows
    def divider(self): pass

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

    operations.render()

    assert "Transport Operations" in fake_st.text()
    assert "No vehicles registered yet" in fake_st.text()
    assert "No drivers registered yet" in fake_st.text()
    assert "sample fleet data" in fake_st.text()
    assert fake_st.rows is None

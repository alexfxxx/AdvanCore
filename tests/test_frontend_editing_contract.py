from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_primary_console_has_one_confirmed_record_manager():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    for identifier in (
        "manage-records",
        "record-manager",
        "record-manager-content",
        "edit-confirmation",
        "confirm-edit-action",
    ):
        assert f'id="{identifier}"' in html
    for tab in ("projects", "knowledge", "fleet", "drivers", "customers", "routes"):
        assert f'data-manager-tab="{tab}"' in html
    assert "/assets/editing.js?v=task-189-1" in html


def test_editing_client_uses_same_origin_confirmation_and_action_token():
    javascript = (ROOT / "frontend" / "editing.js").read_text(encoding="utf-8")

    assert 'readJson("/api/session")' in javascript
    assert '"X-AdvanCore-Action-Token": token' in javascript
    assert "confirmed: true" in javascript
    assert "confirmChange(message, summary)" in javascript
    assert "confirmation.showModal()" in javascript
    assert "expected_content_sha256" in javascript
    assert '"Complete content", record.content' in javascript
    assert 'record.status === "active" ? [edit, archive] : []' in javascript
    assert "fetch(url" in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "http://" not in javascript
    assert "https://" not in javascript
    assert "/api/orchestrations" not in javascript
    assert "launch worker" not in javascript.lower()


def test_editing_client_exposes_only_approved_existing_business_fields():
    javascript = (ROOT / "frontend" / "editing.js").read_text(encoding="utf-8")

    for name in (
        "name",
        "description",
        "title",
        "content",
        "registration_number",
        "make_model",
        "registered_owner_id",
        "manufacture_year",
        "passenger_capacity",
        "vehicle_type",
        "parking_provider",
        "parking_location",
        "parking_monthly_cost",
        "insurance_provider",
        "insurance_annual_amount",
        "road_tax_amount",
        "road_tax_period_months",
        "finance_company",
        "original_loan_amount",
        "monthly_instalment",
        "loan_start_date",
        "loan_term_months",
        "employee_reference",
        "customer_reference",
        "route_code",
        "origin",
        "destination",
    ):
        assert name in javascript
    assert "diesel_invoice" not in javascript
    assert "electric_charging" not in javascript
    assert "password" not in javascript.lower()


def test_customer_profile_contains_recurring_services_without_new_top_level_tab():
    javascript = (ROOT / "frontend" / "editing.js").read_text(encoding="utf-8")
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "Recurring Services stay inside this customer profile" in javascript
    assert "/api/recurring-services" in javascript
    assert "fixed monthly tender service" in javascript
    assert "Open profile" in javascript
    assert 'data-manager-tab="recurring-services"' not in html


def test_driver_profile_contains_private_payroll_history_without_new_top_level_tab():
    javascript = (ROOT / "frontend" / "editing.js").read_text(encoding="utf-8")
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "Private Employment/Payroll history" in javascript
    assert "/api/driver-employment-records" in javascript
    assert "Local / PR — CPF" in javascript
    assert "Foreign worker — levy" in javascript
    assert "Open private profile" in javascript
    assert 'data-manager-tab="payroll"' not in html

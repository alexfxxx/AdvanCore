from datetime import date
from decimal import Decimal, InvalidOperation

from advancore.models import FinancialEntry


FINANCIAL_ENTRY_TYPES = ("income", "expense")


class FinancialEntryValidationError(ValueError): pass


class FinancialEntryService:
    def __init__(self, repository): self._repo = repository

    @staticmethod
    def _optional_identifier(value, label, loader):
        if value is None: return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or loader(value) is None:
            raise FinancialEntryValidationError(f"Select an existing {label}.")
        return value

    @staticmethod
    def _amount(value):
        if isinstance(value, bool): raise FinancialEntryValidationError("Amount is invalid.")
        try:
            number = Decimal(str(value)); stored = number.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError): raise FinancialEntryValidationError("Amount is invalid.") from None
        if not number.is_finite() or number <= 0 or number != stored or stored > Decimal("999999999999.99"):
            raise FinancialEntryValidationError("Amount must be positive with no more than two decimal places.")
        return stored

    def record(self, entry_date, entry_type, amount, currency_code, description=None, trip_id=None, customer_id=None):
        if type(entry_date) is not date: raise FinancialEntryValidationError("Entry date is required.")
        if entry_type not in FINANCIAL_ENTRY_TYPES: raise FinancialEntryValidationError("Entry type is invalid.")
        raw_currency = (currency_code or "").strip()
        if len(raw_currency) != 3 or not all(
            "A" <= character <= "Z" or "a" <= character <= "z"
            for character in raw_currency
        ):
            raise FinancialEntryValidationError("Currency code must be three letters.")
        currency = raw_currency.upper()
        note = (description or "").strip() or None
        if note is not None and len(note) > 200: raise FinancialEntryValidationError("Description must be 200 characters or fewer.")
        trip = self._optional_identifier(trip_id, "trip", self._repo.trip)
        customer = self._optional_identifier(customer_id, "customer", self._repo.customer)
        return self._repo.add(FinancialEntry(entry_date=entry_date, entry_type=entry_type, amount=self._amount(amount), currency_code=currency, description=note, trip_id=trip, customer_id=customer))

    def list_entries(self): return self._repo.list()

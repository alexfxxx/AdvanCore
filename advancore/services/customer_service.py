from collections.abc import Sequence
from sqlalchemy.exc import IntegrityError
from advancore.models import Customer
from advancore.repositories import CustomerRepository
from advancore.services.activity_service import ActivityLogService

CUSTOMER_STATUSES = ("active", "inactive")
class CustomerValidationError(ValueError): pass
class DuplicateCustomerReferenceError(ValueError): pass
class CustomerNotFoundError(ValueError): pass

class CustomerService:
    def __init__(self, repository: CustomerRepository, activity_service: ActivityLogService | None = None): self._repo = repository; self._activity = activity_service
    def create_customer(self, name: str, customer_reference: str | None = None) -> Customer:
        clean_name = " ".join((name or "").strip().split())
        if not clean_name or len(clean_name) > 160: raise CustomerValidationError("Customer name must be 1–160 characters.")
        reference = (customer_reference or "").strip().upper() or None
        if reference and (len(reference) > 40 or any(ch in reference for ch in "\r\n\t")): raise CustomerValidationError("Customer reference must be 40 characters or fewer.")
        if reference and self._repo.get_by_reference(reference): raise DuplicateCustomerReferenceError("That customer reference already exists.")
        try: saved = self._repo.add(Customer(name=clean_name, customer_reference=reference, status="active"))
        except IntegrityError as exc: raise DuplicateCustomerReferenceError("That customer reference already exists.") from exc
        if self._activity: self._activity.record_activity("customer_created", "customer", saved.id)
        return saved
    def set_status(self, identifier: int, status: str) -> Customer:
        if status not in CUSTOMER_STATUSES: raise CustomerValidationError("Customer status is invalid.")
        item = self._repo.get_by_id(identifier)
        if item is None: raise CustomerNotFoundError("The selected customer could not be found.")
        item.status = status; saved = self._repo.save(item)
        if self._activity: self._activity.record_activity("customer_status_changed", "customer", saved.id)
        return saved
    def list_customers(self) -> Sequence[Customer]: return self._repo.list()

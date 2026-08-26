from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from advancore.models import Customer

class CustomerRepository:
    def __init__(self, session: Session): self._session = session
    def add(self, item: Customer) -> Customer: self._session.add(item); self._session.flush(); self._session.refresh(item); return item
    def save(self, item: Customer) -> Customer: self._session.flush(); self._session.refresh(item); return item
    def get_by_id(self, identifier: int) -> Customer | None: return self._session.get(Customer, identifier)
    def get_by_reference(self, value: str) -> Customer | None: return self._session.scalar(select(Customer).where(Customer.customer_reference == value))
    def list(self) -> Sequence[Customer]: return self._session.scalars(select(Customer).order_by(Customer.name, Customer.id)).all()

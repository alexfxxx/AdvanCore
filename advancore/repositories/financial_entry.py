from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import Customer, FinancialEntry, Trip


class FinancialEntryRepository:
    def __init__(self, session: Session): self._session = session
    def trip(self, identifier: int): return self._session.get(Trip, identifier)
    def customer(self, identifier: int): return self._session.get(Customer, identifier)
    def add(self, item): self._session.add(item); self._session.flush(); self._session.refresh(item); return item
    def list(self):
        return self._session.scalars(
            select(FinancialEntry).order_by(
                FinancialEntry.entry_date.desc(), FinancialEntry.id.desc()
            )
        ).all()

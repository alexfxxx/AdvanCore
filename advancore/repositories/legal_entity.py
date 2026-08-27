from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import LegalEntity


class LegalEntityRepository:
    def __init__(self, session: Session): self._session = session
    def add(self, item: LegalEntity) -> LegalEntity: self._session.add(item); self._session.flush(); self._session.refresh(item); return item
    def save(self, item: LegalEntity) -> LegalEntity: self._session.flush(); self._session.refresh(item); return item
    def get_by_id(self, identifier: int) -> LegalEntity | None: return self._session.get(LegalEntity, identifier)
    def get_by_name(self, name: str) -> LegalEntity | None: return self._session.scalar(select(LegalEntity).where(LegalEntity.name == name))
    def list(self) -> Sequence[LegalEntity]: return self._session.scalars(select(LegalEntity).order_by(LegalEntity.name, LegalEntity.id)).all()

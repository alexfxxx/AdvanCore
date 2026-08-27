from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from advancore.models import LegalEntity
from advancore.repositories import LegalEntityRepository

LEGAL_ENTITY_STATUSES = ("active", "inactive")

class LegalEntityValidationError(ValueError): pass
class DuplicateLegalEntityError(ValueError): pass
class LegalEntityNotFoundError(ValueError): pass

class LegalEntityService:
    def __init__(self, repository: LegalEntityRepository): self._repo = repository

    @staticmethod
    def _name(value: str) -> str:
        if any(character in (value or "") for character in "\r\n\t"):
            raise LegalEntityValidationError("Company name must be 1–160 characters.")
        name = " ".join((value or "").strip().split())
        if not name or len(name) > 160:
            raise LegalEntityValidationError("Company name must be 1–160 characters.")
        return name

    def create(self, name: str) -> LegalEntity:
        clean = self._name(name)
        if self._repo.get_by_name(clean): raise DuplicateLegalEntityError("That company name already exists.")
        try: return self._repo.add(LegalEntity(name=clean, status="active"))
        except IntegrityError as exc: raise DuplicateLegalEntityError("That company name already exists.") from exc

    def set_status(self, identifier: int, status: str) -> LegalEntity:
        if status not in LEGAL_ENTITY_STATUSES: raise LegalEntityValidationError("Company status is invalid.")
        item = self._repo.get_by_id(identifier)
        if item is None: raise LegalEntityNotFoundError("The selected company could not be found.")
        item.status = status
        return self._repo.save(item)

    def list_entities(self) -> Sequence[LegalEntity]: return self._repo.list()

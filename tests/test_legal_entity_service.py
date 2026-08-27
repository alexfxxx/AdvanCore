import pytest
from sqlalchemy import create_engine

from advancore.models import Base
from advancore.repositories import LegalEntityRepository
from advancore.services.database import create_session_factory, session_scope
from advancore.services.legal_entity_service import (
    DuplicateLegalEntityError, LegalEntityService, LegalEntityValidationError,
)

def factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)

def test_company_normalization_duplicate_lifecycle_and_persistence():
    sessions = factory()
    with session_scope(sessions) as session:
        service = LegalEntityService(LegalEntityRepository(session))
        company = service.create("  AdvanCore   Transport  ")
        identifier = company.id
        assert company.name == "AdvanCore Transport"
        with pytest.raises(DuplicateLegalEntityError): service.create("AdvanCore Transport")
        assert service.set_status(identifier, "inactive").status == "inactive"
    with session_scope(sessions) as session:
        assert LegalEntityService(LegalEntityRepository(session)).list_entities()[0].id == identifier

@pytest.mark.parametrize("name", ["", " ", "x" * 161, "bad\nname"])
def test_company_name_is_bounded(name):
    sessions = factory()
    with session_scope(sessions) as session:
        with pytest.raises(LegalEntityValidationError): LegalEntityService(LegalEntityRepository(session)).create(name)

import pytest
from sqlalchemy import create_engine
from advancore.models import Base
from advancore.repositories import RouteRepository
from advancore.services.database import create_session_factory,session_scope
from advancore.services.route_service import RouteService,RouteValidationError,DuplicateRouteError
def factory():
    e=create_engine("sqlite:///:memory:"); Base.metadata.create_all(e); return create_session_factory(e)
def test_route_create_list_status():
    db=factory()
    with session_scope(db) as s:
        service=RouteService(RouteRepository(s)); x=service.create_route(" r-1 "," Depot "," City "); i=x.id; assert (x.route_code,x.origin,x.destination)==("R-1","Depot","City")
    with session_scope(db) as s:
        service=RouteService(RouteRepository(s)); assert service.set_status(i,"inactive").status=="inactive"; assert len(service.list_routes())==1
def test_route_rejects_invalid_and_duplicate():
    db=factory()
    with session_scope(db) as s:
        service=RouteService(RouteRepository(s))
        with pytest.raises(RouteValidationError): service.create_route("R","Same","same")
        service.create_route("R","A","B")
        with pytest.raises(DuplicateRouteError): service.create_route("r","C","D")

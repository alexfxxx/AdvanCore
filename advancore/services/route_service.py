from sqlalchemy.exc import IntegrityError
from advancore.models import Route
from advancore.repositories import RouteRepository
ROUTE_STATUSES=("active","inactive")
class RouteValidationError(ValueError): pass
class DuplicateRouteError(ValueError): pass
class RouteNotFoundError(ValueError): pass
class RouteService:
    def __init__(self,repo): self.repo=repo
    def create_route(self,code,origin,destination):
        c=(code or "").strip().upper(); o=" ".join((origin or "").split()); d=" ".join((destination or "").split())
        if not c or len(c)>40: raise RouteValidationError("Route code must be 1–40 characters.")
        if not o or not d or len(o)>160 or len(d)>160: raise RouteValidationError("Origin and destination are required and must be 160 characters or fewer.")
        if o.casefold()==d.casefold(): raise RouteValidationError("Origin and destination must be different.")
        if self.repo.get_by_code(c): raise DuplicateRouteError("That route code already exists.")
        try: return self.repo.add(Route(route_code=c,origin=o,destination=d,status="active"))
        except IntegrityError as exc: raise DuplicateRouteError("That route code already exists.") from exc
    def set_status(self,i,status):
        if status not in ROUTE_STATUSES: raise RouteValidationError("Route status is invalid.")
        item=self.repo.get_by_id(i)
        if item is None: raise RouteNotFoundError("The selected route could not be found.")
        item.status=status; return self.repo.save(item)
    def list_routes(self): return self.repo.list()

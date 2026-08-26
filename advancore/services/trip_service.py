from datetime import date
from sqlalchemy.exc import IntegrityError
from advancore.models import Trip
TRIP_STATUSES=("planned","completed","cancelled")
class TripValidationError(ValueError): pass
class DuplicateTripError(ValueError): pass
class TripNotFoundError(ValueError): pass
class TripService:
    def __init__(self,repo): self.repo=repo
    def create_trip(self,reference,route_id,service_date):
        ref=(reference or "").strip().upper()
        if not ref or len(ref)>40: raise TripValidationError("Trip reference must be 1–40 characters.")
        if isinstance(route_id,bool) or not isinstance(route_id,int) or self.repo.route(route_id) is None: raise TripValidationError("Select an existing route.")
        if type(service_date) is not date: raise TripValidationError("Service date is required.")
        if self.repo.by_reference(ref): raise DuplicateTripError("That trip reference already exists.")
        try:return self.repo.add(Trip(trip_reference=ref,route_id=route_id,service_date=service_date,status="planned"))
        except IntegrityError as exc: raise DuplicateTripError("That trip reference already exists.") from exc
    def set_status(self,i,status):
        if status not in TRIP_STATUSES: raise TripValidationError("Trip status is invalid.")
        x=self.repo.get(i)
        if x is None: raise TripNotFoundError("The selected trip could not be found.")
        x.status=status;return self.repo.save(x)
    def list_trips(self):return self.repo.list()

from sqlalchemy import select
from sqlalchemy.orm import Session
from advancore.models import Route,Trip
class TripRepository:
    def __init__(self,s:Session): self.s=s
    def route(self,i): return self.s.get(Route,i)
    def by_reference(self,r): return self.s.scalar(select(Trip).where(Trip.trip_reference==r))
    def add(self,x): self.s.add(x);self.s.flush();self.s.refresh(x);return x
    def save(self,x): self.s.flush();self.s.refresh(x);return x
    def get(self,i): return self.s.get(Trip,i)
    def list(self): return self.s.scalars(select(Trip).order_by(Trip.service_date,Trip.trip_reference)).all()

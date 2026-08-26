from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from advancore.models import Route
class RouteRepository:
    def __init__(self, session: Session): self.s=session
    def add(self,x): self.s.add(x); self.s.flush(); self.s.refresh(x); return x
    def save(self,x): self.s.flush(); self.s.refresh(x); return x
    def get_by_id(self,i): return self.s.get(Route,i)
    def get_by_code(self,c): return self.s.scalar(select(Route).where(Route.route_code==c))
    def list(self)->Sequence[Route]: return self.s.scalars(select(Route).order_by(Route.route_code)).all()

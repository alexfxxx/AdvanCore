"""Loopback-only local business registers introduced by the operations workspace."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from advancore.api.routes.orchestration import require_confirmation, require_local_action, require_loopback_peer
from advancore.models import Driver, MaintenanceEntry, RecurringRouteAssignment, RecurringService, Subcontractor, SubcontractorDriver, SubcontractorVehicle, Vehicle
from advancore.services.database import session_scope


router = APIRouter(prefix="/api", tags=["local business operations"])


class Confirmed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool


class SubcontractorCreate(Confirmed):
    company_name: str = Field(min_length=1, max_length=160)


class SubcontractorDriverCreate(Confirmed):
    name: str = Field(min_length=1, max_length=120)
    contact_number: str | None = Field(default=None, max_length=40)


class SubcontractorVehicleCreate(Confirmed):
    vehicle_number: str = Field(min_length=1, max_length=32)
    capacity: int | None = Field(default=None, gt=0)


class MaintenanceCreate(Confirmed):
    vehicle_id: int = Field(gt=0)
    service_date: date
    vendor: str = Field(min_length=1, max_length=160)
    service_type: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    remarks: str | None = Field(default=None, max_length=300)


class RouteAssignmentCreate(Confirmed):
    recurring_service_id: int = Field(gt=0)
    assignment_type: str = Field(pattern="^(own_fleet|subcontractor)$")
    vehicle_id: int | None = Field(default=None, gt=0)
    driver_id: int | None = Field(default=None, gt=0)
    subcontractor_vehicle_id: int | None = Field(default=None, gt=0)
    subcontractor_driver_id: int | None = Field(default=None, gt=0)
    monthly_subcontractor_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    effective_start_date: date
    remarks: str | None = Field(default=None, max_length=300)


def _confirm(payload: Confirmed) -> None:
    require_confirmation(payload.confirmed)


def _subcontractor_dict(item: Subcontractor, drivers=(), vehicles=()) -> dict:
    return {
        "id": item.id, "company_name": item.company_name, "status": item.status,
        "drivers": [{"id": row.id, "name": row.name, "contact_number": row.contact_number} for row in drivers],
        "vehicles": [{"id": row.id, "vehicle_number": row.vehicle_number, "capacity": row.capacity} for row in vehicles],
    }


@router.get("/subcontractors", dependencies=[Depends(require_loopback_peer)])
def list_subcontractors(response: Response) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    with session_scope() as session:
        items = session.scalars(select(Subcontractor).order_by(Subcontractor.company_name)).all()
        drivers = session.scalars(select(SubcontractorDriver)).all()
        vehicles = session.scalars(select(SubcontractorVehicle)).all()
        return [_subcontractor_dict(item, [d for d in drivers if d.subcontractor_id == item.id], [v for v in vehicles if v.subcontractor_id == item.id]) for item in items]


@router.post("/subcontractors", status_code=201, dependencies=[Depends(require_local_action)])
def create_subcontractor(payload: SubcontractorCreate) -> dict:
    _confirm(payload)
    name = payload.company_name.strip()
    with session_scope() as session:
        if session.scalar(select(Subcontractor).where(Subcontractor.company_name == name)):
            raise HTTPException(status.HTTP_409_CONFLICT, "A subcontractor with this company name already exists.")
        item = Subcontractor(company_name=name, status="active")
        session.add(item); session.flush()
        return _subcontractor_dict(item)


@router.post("/subcontractors/{identifier}/archive", dependencies=[Depends(require_local_action)])
def archive_subcontractor(identifier: int, payload: Confirmed) -> dict:
    _confirm(payload)
    with session_scope() as session:
        item = session.get(Subcontractor, identifier)
        if item is None: raise HTTPException(status.HTTP_404_NOT_FOUND, "Subcontractor not found.")
        item.status = "archived"; session.flush()
        return _subcontractor_dict(item)


@router.post("/subcontractors/{identifier}/drivers", status_code=201, dependencies=[Depends(require_local_action)])
def add_subcontractor_driver(identifier: int, payload: SubcontractorDriverCreate) -> dict:
    _confirm(payload)
    with session_scope() as session:
        contractor = session.get(Subcontractor, identifier)
        if contractor is None: raise HTTPException(status.HTTP_404_NOT_FOUND, "Subcontractor not found.")
        if contractor.status != "active": raise HTTPException(status.HTTP_409_CONFLICT, "Archived subcontractors cannot be changed.")
        item = SubcontractorDriver(subcontractor_id=identifier, name=payload.name.strip(), contact_number=(payload.contact_number or "").strip() or None)
        session.add(item); session.flush()
        return {"id": item.id, "name": item.name, "contact_number": item.contact_number}


@router.post("/subcontractors/{identifier}/vehicles", status_code=201, dependencies=[Depends(require_local_action)])
def add_subcontractor_vehicle(identifier: int, payload: SubcontractorVehicleCreate) -> dict:
    _confirm(payload)
    with session_scope() as session:
        contractor = session.get(Subcontractor, identifier)
        if contractor is None: raise HTTPException(status.HTTP_404_NOT_FOUND, "Subcontractor not found.")
        if contractor.status != "active": raise HTTPException(status.HTTP_409_CONFLICT, "Archived subcontractors cannot be changed.")
        item = SubcontractorVehicle(subcontractor_id=identifier, vehicle_number=payload.vehicle_number.strip().upper(), capacity=payload.capacity)
        session.add(item); session.flush()
        return {"id": item.id, "vehicle_number": item.vehicle_number, "capacity": item.capacity}


@router.get("/maintenance-entries", dependencies=[Depends(require_loopback_peer)])
def list_maintenance(response: Response) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    with session_scope() as session:
        rows = session.execute(select(MaintenanceEntry, Vehicle).join(Vehicle, Vehicle.id == MaintenanceEntry.vehicle_id).order_by(MaintenanceEntry.service_date.desc())).all()
        return [{"id": item.id, "vehicle_id": item.vehicle_id, "vehicle_number": vehicle.registration_number, "service_date": item.service_date, "vendor": item.vendor, "service_type": item.service_type, "amount": item.amount, "remarks": item.remarks} for item, vehicle in rows]


@router.post("/maintenance-entries", status_code=201, dependencies=[Depends(require_local_action)])
def create_maintenance(payload: MaintenanceCreate) -> dict:
    _confirm(payload)
    with session_scope() as session:
        vehicle = session.get(Vehicle, payload.vehicle_id)
        if vehicle is None: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select an existing vehicle.")
        item = MaintenanceEntry(vehicle_id=payload.vehicle_id, service_date=payload.service_date, vendor=payload.vendor.strip(), service_type=payload.service_type.strip(), amount=payload.amount, remarks=(payload.remarks or "").strip() or None)
        session.add(item); session.flush()
        return {"id": item.id, "vehicle_id": item.vehicle_id, "vehicle_number": vehicle.registration_number, "service_date": item.service_date, "vendor": item.vendor, "service_type": item.service_type, "amount": item.amount, "remarks": item.remarks}


@router.get("/recurring-route-assignments", dependencies=[Depends(require_loopback_peer)])
def list_route_assignments(response: Response) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    with session_scope() as session:
        assignments = session.scalars(select(RecurringRouteAssignment).order_by(RecurringRouteAssignment.effective_start_date.desc())).all()
        result = []
        for item in assignments:
            vehicle = session.get(Vehicle, item.vehicle_id) if item.vehicle_id else None
            driver = session.get(Driver, item.driver_id) if item.driver_id else None
            sub_vehicle = session.get(SubcontractorVehicle, item.subcontractor_vehicle_id) if item.subcontractor_vehicle_id else None
            sub_driver = session.get(SubcontractorDriver, item.subcontractor_driver_id) if item.subcontractor_driver_id else None
            contractor = session.get(Subcontractor, sub_vehicle.subcontractor_id) if sub_vehicle else None
            result.append({"id": item.id, "recurring_service_id": item.recurring_service_id, "assignment_type": item.assignment_type, "vehicle_id": item.vehicle_id, "vehicle_number": vehicle.registration_number if vehicle else (sub_vehicle.vehicle_number if sub_vehicle else None), "driver_id": item.driver_id, "driver_name": driver.name if driver else (sub_driver.name if sub_driver else None), "contact_number": sub_driver.contact_number if sub_driver else None, "subcontractor_vehicle_id": item.subcontractor_vehicle_id, "subcontractor_driver_id": item.subcontractor_driver_id, "subcontractor_name": contractor.company_name if contractor else None, "monthly_subcontractor_cost": item.monthly_subcontractor_cost, "effective_start_date": item.effective_start_date, "effective_end_date": item.effective_end_date, "status": item.status, "remarks": item.remarks})
        return result


@router.post("/recurring-route-assignments", status_code=201, dependencies=[Depends(require_local_action)])
def create_route_assignment(payload: RouteAssignmentCreate) -> dict:
    _confirm(payload)
    with session_scope() as session:
        if session.get(RecurringService, payload.recurring_service_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select an existing recurring route.")
        if payload.assignment_type == "own_fleet":
            if payload.vehicle_id is None or session.get(Vehicle, payload.vehicle_id) is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an own-fleet vehicle.")
            if payload.driver_id is not None and session.get(Driver, payload.driver_id) is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an existing driver.")
            if payload.subcontractor_vehicle_id or payload.subcontractor_driver_id or payload.monthly_subcontractor_cost is not None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Do not mix subcontractor costs with an own-fleet assignment.")
        else:
            sub_vehicle = session.get(SubcontractorVehicle, payload.subcontractor_vehicle_id) if payload.subcontractor_vehicle_id else None
            if sub_vehicle is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a subcontractor vehicle.")
            contractor = session.get(Subcontractor, sub_vehicle.subcontractor_id)
            if contractor is None or contractor.status != "active": raise HTTPException(status.HTTP_409_CONFLICT, "Archived subcontractors cannot receive new route assignments.")
            sub_driver = session.get(SubcontractorDriver, payload.subcontractor_driver_id) if payload.subcontractor_driver_id else None
            if payload.subcontractor_driver_id is not None and sub_driver is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an existing subcontractor driver.")
            if sub_driver is not None and sub_driver.subcontractor_id != sub_vehicle.subcontractor_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "The subcontractor driver and vehicle must belong to the same company.")
            if payload.monthly_subcontractor_cost is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter the fixed monthly subcontractor cost.")
            if payload.vehicle_id or payload.driver_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose either own fleet or subcontractor, not both.")
        current = session.scalars(select(RecurringRouteAssignment).where(RecurringRouteAssignment.recurring_service_id == payload.recurring_service_id, RecurringRouteAssignment.status == "active")).all()
        for existing in current:
            if payload.effective_start_date <= existing.effective_start_date:
                raise HTTPException(status.HTTP_409_CONFLICT, "A replacement assignment must start after the current assignment starts.")
            existing.status = "ended"
            existing.effective_end_date = payload.effective_start_date - timedelta(days=1)
        item = RecurringRouteAssignment(**payload.model_dump(exclude={"confirmed"}), status="active")
        session.add(item)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "This route already has an active assignment.") from exc
        return {"id": item.id, "recurring_service_id": item.recurring_service_id, "assignment_type": item.assignment_type, "status": item.status}

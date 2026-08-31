"""Confirmed loopback-only routes for existing application editing services."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from advancore.api.editing_gateway import (
    EditingConflictError,
    EditingNotFoundError,
    EditingUnavailableError,
    EditingValidationError,
)
from advancore.api.routes.orchestration import (
    require_confirmation,
    require_local_action,
)
from advancore.api.schemas import (
    ConfirmedRequest,
    CustomerCreateRequest,
    CustomerResponse,
    CustomerStatusRequest,
    DriverCreateRequest,
    DriverResponse,
    DriverStatusRequest,
    KnowledgeApproveRequest,
    KnowledgeDraftRequest,
    KnowledgeResponse,
    LegalEntityCreateRequest,
    LegalEntityResponse,
    ProjectCreateRequest,
    ProjectEditRequest,
    ProjectResponse,
    RouteCreateRequest,
    RouteResponse,
    RouteStatusRequest,
    VehicleCreateRequest,
    VehicleDetailsRequest,
    VehicleResponse,
    VehicleStatusRequest,
)


router = APIRouter(
    prefix="/api",
    tags=["local editing"],
    dependencies=[Depends(require_local_action)],
)


def _confirmed(payload: ConfirmedRequest) -> None:
    require_confirmation(payload.confirmed)


def _call(action):
    try:
        return action()
    except EditingValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EditingNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EditingConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EditingUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The local edit could not be completed safely.",
        ) from exc


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreateRequest, request: Request) -> ProjectResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.create_project(
            payload.name, payload.description
        )
    )


@router.post("/projects/{identifier}/edit", response_model=ProjectResponse)
def edit_project(
    identifier: int, payload: ProjectEditRequest, request: Request
) -> ProjectResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.edit_project(
            identifier, payload.name, payload.description
        )
    )


@router.post("/projects/{identifier}/archive", response_model=ProjectResponse)
def archive_project(
    identifier: int, payload: ConfirmedRequest, request: Request
) -> ProjectResponse:
    _confirmed(payload)
    return _call(lambda: request.app.state.edit_gateway.archive_project(identifier))


@router.post("/knowledge", response_model=KnowledgeResponse, status_code=201)
def create_knowledge(
    payload: KnowledgeDraftRequest, request: Request
) -> KnowledgeResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.create_knowledge(
            payload.title, payload.content
        )
    )


@router.post("/knowledge/{identifier}/edit", response_model=KnowledgeResponse)
def edit_knowledge(
    identifier: int, payload: KnowledgeDraftRequest, request: Request
) -> KnowledgeResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.edit_knowledge(
            identifier, payload.title, payload.content
        )
    )


@router.post("/knowledge/{identifier}/approve", response_model=KnowledgeResponse)
def approve_knowledge(
    identifier: int, payload: KnowledgeApproveRequest, request: Request
) -> KnowledgeResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.approve_knowledge(
            identifier,
            payload.expected_updated_at,
            payload.expected_content_sha256,
        )
    )


@router.post("/knowledge/{identifier}/archive", response_model=KnowledgeResponse)
def archive_knowledge(
    identifier: int, payload: ConfirmedRequest, request: Request
) -> KnowledgeResponse:
    _confirmed(payload)
    return _call(lambda: request.app.state.edit_gateway.archive_knowledge(identifier))


@router.post(
    "/knowledge/{identifier}/replacement",
    response_model=KnowledgeResponse,
    status_code=201,
)
def replace_knowledge(
    identifier: int, payload: ConfirmedRequest, request: Request
) -> KnowledgeResponse:
    _confirmed(payload)
    return _call(lambda: request.app.state.edit_gateway.replace_knowledge(identifier))


@router.post("/legal-entities", response_model=LegalEntityResponse, status_code=201)
def create_legal_entity(
    payload: LegalEntityCreateRequest, request: Request
) -> LegalEntityResponse:
    _confirmed(payload)
    return _call(lambda: request.app.state.edit_gateway.create_legal_entity(payload.name))


@router.post("/vehicles", response_model=VehicleResponse, status_code=201)
def create_vehicle(payload: VehicleCreateRequest, request: Request) -> VehicleResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.create_vehicle(
            payload.registration_number, payload.make_model
        )
    )


@router.post("/vehicles/{identifier}/status", response_model=VehicleResponse)
def set_vehicle_status(
    identifier: int, payload: VehicleStatusRequest, request: Request
) -> VehicleResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.set_vehicle_status(
            identifier, payload.status
        )
    )


@router.post("/vehicles/{identifier}/details", response_model=VehicleResponse)
def update_vehicle_details(
    identifier: int, payload: VehicleDetailsRequest, request: Request
) -> VehicleResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.update_vehicle_details(
            identifier, payload
        )
    )


@router.post("/drivers", response_model=DriverResponse, status_code=201)
def create_driver(payload: DriverCreateRequest, request: Request) -> DriverResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.create_driver(
            payload.name, payload.employee_reference
        )
    )


@router.post("/drivers/{identifier}/status", response_model=DriverResponse)
def set_driver_status(
    identifier: int, payload: DriverStatusRequest, request: Request
) -> DriverResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.set_driver_status(
            identifier, payload.status
        )
    )


@router.post("/customers", response_model=CustomerResponse, status_code=201)
def create_customer(
    payload: CustomerCreateRequest, request: Request
) -> CustomerResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.create_customer(
            payload.name, payload.customer_reference
        )
    )


@router.post("/customers/{identifier}/status", response_model=CustomerResponse)
def set_customer_status(
    identifier: int, payload: CustomerStatusRequest, request: Request
) -> CustomerResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.set_customer_status(
            identifier, payload.status
        )
    )


@router.post("/routes", response_model=RouteResponse, status_code=201)
def create_route(payload: RouteCreateRequest, request: Request) -> RouteResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.create_route(
            payload.route_code, payload.origin, payload.destination
        )
    )


@router.post("/routes/{identifier}/status", response_model=RouteResponse)
def set_route_status(
    identifier: int, payload: RouteStatusRequest, request: Request
) -> RouteResponse:
    _confirmed(payload)
    return _call(
        lambda: request.app.state.edit_gateway.set_route_status(
            identifier, payload.status
        )
    )

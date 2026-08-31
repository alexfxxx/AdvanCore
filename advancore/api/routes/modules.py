"""Read-only module catalog projection for local presentation clients."""

from fastapi import APIRouter

from advancore.api.schemas import ModuleResponse
from advancore.module_registry import module_catalog


router = APIRouter(prefix="/api", tags=["modules"])


@router.get("/modules", response_model=list[ModuleResponse])
def list_modules() -> list[ModuleResponse]:
    responses: list[ModuleResponse] = []
    for module in module_catalog():
        surfaces = []
        if module.frontend_anchor is not None:
            surfaces.append("primary_console")
        if module.streamlit_page is not None:
            surfaces.append("temporary_streamlit_admin")
        responses.append(
            ModuleResponse(
                module_id=module.module_id,
                label=module.label,
                area=module.area.value,
                maturity=module.maturity.value,
                presentation_surfaces=surfaces,
                api_prefixes=list(module.api_prefixes),
            )
        )
    return responses

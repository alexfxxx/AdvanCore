"""Disabled-by-default voice transport boundary."""

from fastapi import APIRouter, WebSocket


router = APIRouter(tags=["voice"])


@router.websocket("/ws/transcription")
async def transcription_hook(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "status",
            "state": "disabled",
            "message": (
                "Live transcription is not configured. Audio is not accepted "
                "or stored by this scaffold."
            ),
        }
    )
    await websocket.close(code=1000)

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.schemas.agent import AgentCommandResponse, AgentStartRequest, AgentStatusResponse
from app.services.agent_event_bus import agent_event_bus
from app.services.agent_service import autonomous_agent


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/status", response_model=AgentStatusResponse)
def get_agent_status(_: object = Depends(get_current_user)) -> AgentStatusResponse:
    return autonomous_agent.status()


@router.post("/start", response_model=AgentCommandResponse)
def start_agent(
    payload: AgentStartRequest,
    _: object = Depends(get_current_user),
) -> AgentCommandResponse:
    try:
        return autonomous_agent.start(symbol=payload.symbol, launched_from=payload.launched_from)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stop", response_model=AgentCommandResponse)
def stop_agent(_: object = Depends(get_current_user)) -> AgentCommandResponse:
    return autonomous_agent.stop()


@router.get("/stream")
async def stream_agent_events(_: object = Depends(get_current_user)) -> StreamingResponse:
    status = autonomous_agent.status()

    async def event_generator():
        yield f"event: status\ndata: {json.dumps(status.model_dump(mode='json'))}\n\n"
        async with agent_event_bus.subscribe() as queue:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                stream_name = message.get("stream", "agent_event")
                payload = message.get("payload", message)
                yield f"event: {stream_name}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

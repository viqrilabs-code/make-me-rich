from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AgentEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict]]] = {}
        self._lock = threading.Lock()

    def publish(self, event: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers.items())
        for subscriber_id, (loop, queue) in subscribers:
            try:
                loop.call_soon_threadsafe(self._enqueue, queue, event)
            except RuntimeError:
                self.unsubscribe(subscriber_id)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict]]:
        subscriber_id = str(uuid.uuid4())
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers[subscriber_id] = (loop, queue)
        try:
            yield queue
        finally:
            self.unsubscribe(subscriber_id)

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def _enqueue(self, queue: asyncio.Queue[dict], event: dict) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(event)


agent_event_bus = AgentEventBus()

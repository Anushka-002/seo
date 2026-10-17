"""In-process pub/sub so SSE clients can follow an analysis (with replay for late joiners)."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field

TERMINAL = {"done", "error"}
FORGET_AFTER_SECONDS = 600


@dataclass(frozen=True)
class ProgressEvent:
    """One progress update."""

    analysis_id: str
    stage: str  # queued | searching | scraping | indexing | analyzing | generating | done | error
    status: str  # running | done | error
    message: str
    progress: int  # 0-100
    seq: int = 0
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressBroker:
    """Stores each analysis' event history and fans new events out to subscribers."""

    def __init__(self) -> None:
        self._history: dict[str, list[ProgressEvent]] = {}
        self._subs: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}

    def publish(
        self, analysis_id: str, stage: str, message: str, progress: int,
        status: str = "running", data: dict | None = None,
    ) -> ProgressEvent:  # fmt: skip
        history = self._history.setdefault(analysis_id, [])
        event = ProgressEvent(
            analysis_id, stage, status, message, progress, seq=len(history), data=data or {}
        )
        history.append(event)
        for q in self._subs.get(analysis_id, []):
            q.put_nowait(event)
        if status in TERMINAL:
            try:
                asyncio.get_running_loop().call_later(
                    FORGET_AFTER_SECONDS, self.forget, analysis_id
                )
            except RuntimeError:
                pass
        return event

    def history(self, analysis_id: str) -> list[ProgressEvent]:
        return list(self._history.get(analysis_id, []))

    def is_known(self, analysis_id: str) -> bool:
        return analysis_id in self._history

    def forget(self, analysis_id: str) -> None:
        self._history.pop(analysis_id, None)
        self._subs.pop(analysis_id, None)

    async def subscribe(self, analysis_id: str) -> AsyncIterator[ProgressEvent]:
        """Yield stored events first, then live ones, ending after a terminal event."""
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        for event in self._history.get(analysis_id, []):
            queue.put_nowait(event)
        self._subs.setdefault(analysis_id, []).append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
                if event.status in TERMINAL:
                    return
        finally:
            subs = self._subs.get(analysis_id, [])
            if queue in subs:
                subs.remove(queue)


broker = ProgressBroker()

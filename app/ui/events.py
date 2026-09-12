from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable


EventListener = Callable[["IRISEvent"], None]


@dataclass(frozen=True)
class IRISEvent:
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=monotonic)


class IRISEventBus:
    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(
        self,
        listener: EventListener,
    ) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(
        self,
        listener: EventListener,
    ) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def emit(
        self,
        name: str,
        **data: Any,
    ) -> IRISEvent:
        event = IRISEvent(
            name=name,
            data=data,
        )

        for listener in tuple(self._listeners):
            try:
                listener(event)
            except Exception:
                # La telemetria non deve mai bloccare IRIS.
                continue

        return event
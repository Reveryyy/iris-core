from __future__ import annotations

import time
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.result import ToolResult


class WaitTool(Tool):
    """
    Attende per un numero di secondi.

    Il tool è intenzionalmente limitato a un intervallo massimo
    per evitare che un piano possa bloccare indefinitamente l'Agent Loop.
    """

    MAX_SECONDS = 30.0

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="wait",
            description=(
                "Attende per un breve periodo di tempo prima "
                "di continuare con il passo successivo. "
                "Usalo quando l'utente richiede esplicitamente "
                "di aspettare o quando una pausa temporale fa "
                "parte dell'azione richiesta."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": (
                            "Numero di secondi da attendere."
                        ),
                    },
                },
                "required": [
                    "seconds",
                ],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset(),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:

        seconds = arguments.get(
            "seconds"
        )

        if isinstance(
            seconds,
            bool,
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il valore 'seconds' deve essere "
                    "un numero."
                ),
            )

        if not isinstance(
            seconds,
            (int, float),
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il valore 'seconds' deve essere "
                    "un numero."
                ),
            )

        seconds = float(
            seconds
        )

        if seconds < 0:
            return ToolResult(
                success=False,
                error=(
                    "Il tempo di attesa non può essere negativo."
                ),
            )

        if seconds > self.MAX_SECONDS:
            return ToolResult(
                success=False,
                error=(
                    f"Il tempo di attesa non può superare "
                    f"{self.MAX_SECONDS:.1f} secondi."
                ),
            )

        started = time.perf_counter()

        try:
            time.sleep(
                seconds
            )

        except (KeyboardInterrupt, SystemExit):
            raise

        elapsed = (
            time.perf_counter()
            - started
        )

        return ToolResult(
            success=True,
            output={
                "requested_seconds": seconds,
                "elapsed_seconds": elapsed,
            },
        )


__all__ = [
    "WaitTool",
]
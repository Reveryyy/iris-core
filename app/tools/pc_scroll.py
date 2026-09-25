from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

MIN_NOTCHES = -20
MAX_NOTCHES = 20


def _configure_function(
    function: Any,
    argtypes: list[Any] | None = None,
    restype: Any | None = None,
) -> None:
    if (
        argtypes is not None
        and hasattr(
            function,
            "argtypes",
        )
    ):
        function.argtypes = argtypes

    if (
        restype is not None
        and hasattr(
            function,
            "restype",
        )
    ):
        function.restype = restype


class ScrollMouseTool(Tool):
    """
    Esegue lo scroll verticale della rotella del mouse.

    Un valore positivo fa scorrere verso l'alto.
    Un valore negativo fa scorrere verso il basso.
    """

    def __init__(
        self,
        min_notches: int = MIN_NOTCHES,
        max_notches: int = MAX_NOTCHES,
    ) -> None:
        if (
            isinstance(
                min_notches,
                bool,
            )
            or not isinstance(
                min_notches,
                int,
            )
        ):
            raise TypeError(
                "min_notches deve essere un intero."
            )

        if (
            isinstance(
                max_notches,
                bool,
            )
            or not isinstance(
                max_notches,
                int,
            )
        ):
            raise TypeError(
                "max_notches deve essere un intero."
            )

        if min_notches >= max_notches:
            raise ValueError(
                "min_notches deve essere minore di max_notches."
            )

        self.min_notches = min_notches
        self.max_notches = max_notches

        self._definition = ToolDefinition(
            name="scroll_mouse",
            description=(
                "Esegue lo scroll verticale del mouse. "
                "Un valore positivo di 'notches' scorre verso "
                "l'alto, un valore negativo verso il basso. "
                "Il valore rappresenta il numero di tacche della "
                "rotella."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "notches": {
                        "type": "integer",
                        "description": (
                            "Numero di tacche della rotella. "
                            "Positivo = verso l'alto, "
                            "negativo = verso il basso."
                        ),
                        "minimum": min_notches,
                        "maximum": max_notches,
                    },
                },
                "required": [
                    "notches",
                ],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset(
                {
                    Permission.GUI.value,
                }
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        notches = arguments.get(
            "notches"
        )

        if (
            isinstance(
                notches,
                bool,
            )
            or not isinstance(
                notches,
                int,
            )
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il valore 'notches' deve essere "
                    "un intero."
                ),
            )

        if (
            notches < self.min_notches
            or notches > self.max_notches
        ):
            return ToolResult(
                success=False,
                error=(
                    f"Il numero di tacche deve essere "
                    f"compreso tra {self.min_notches} e "
                    f"{self.max_notches}."
                ),
            )

        if notches == 0:
            return ToolResult(
                success=False,
                error=(
                    "Il numero di tacche non può essere zero."
                ),
            )

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "Lo scroll del mouse è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        mouse_event = user32.mouse_event

        _configure_function(
            mouse_event,
            argtypes=[
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_ulong,
            ],
            restype=None,
        )

        delta = (
            notches * WHEEL_DELTA
        )

        unsigned_delta = (
            delta & 0xFFFFFFFF
        )

        try:
            mouse_event(
                MOUSEEVENTF_WHEEL,
                0,
                0,
                unsigned_delta,
                0,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile eseguire lo scroll: {error}"
                ),
            )

        except (
            OverflowError,
            ValueError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile convertire il valore "
                    f"di scroll: {error}"
                ),
            )

        direction = (
            "up"
            if notches > 0
            else "down"
        )

        return ToolResult(
            success=True,
            output={
                "notches": notches,
                "direction": direction,
                "wheel_delta": delta,
            },
        )


__all__ = [
    "ScrollMouseTool",
]
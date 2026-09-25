from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _virtual_screen_bounds(
    user32: Any,
) -> tuple[int, int, int, int]:
    get_metrics = user32.GetSystemMetrics

    if hasattr(
        get_metrics,
        "argtypes",
    ):
        get_metrics.argtypes = [
            ctypes.c_int,
        ]

    if hasattr(
        get_metrics,
        "restype",
    ):
        get_metrics.restype = ctypes.c_int

    left = get_metrics(
        SM_XVIRTUALSCREEN
    )
    top = get_metrics(
        SM_YVIRTUALSCREEN
    )
    width = get_metrics(
        SM_CXVIRTUALSCREEN
    )
    height = get_metrics(
        SM_CYVIRTUALSCREEN
    )

    if width <= 0 or height <= 0:
        raise OSError(
            "Impossibile determinare il desktop virtuale."
        )

    return (
        left,
        top,
        width,
        height,
    )


class ClickMouseTool(Tool):
    """
    Esegue un click sinistro del mouse a coordinate specifiche
    dello schermo.
    """

    def __init__(
        self,
        click_delay_seconds: float = 0.05,
    ) -> None:

        self.click_delay_seconds = click_delay_seconds

        self._definition = ToolDefinition(
            name="click_mouse",
            description=(
                "Esegue un click sinistro del mouse alle "
                "coordinate indicate sullo schermo."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": (
                            "Coordinata orizzontale del click."
                        ),
                    },
                    "y": {
                        "type": "integer",
                        "description": (
                            "Coordinata verticale del click."
                        ),
                    },
                },
                "required": [
                    "x",
                    "y",
                ],
                "additionalProperties": False,
            },
            risk_level="medium",
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

        x = arguments.get("x")
        y = arguments.get("y")

        if isinstance(x, bool) or not isinstance(x, int):
            return ToolResult(
                success=False,
                error="La coordinata 'x' deve essere un intero.",
            )

        if isinstance(y, bool) or not isinstance(y, int):
            return ToolResult(
                success=False,
                error="La coordinata 'y' deve essere un intero.",
            )

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il controllo del mouse è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        try:
            virtual_left, virtual_top, virtual_width, virtual_height = (
                _virtual_screen_bounds(
                    user32
                )
            )
        except OSError as error:
            return ToolResult(
                success=False,
                error=str(error),
            )

        right = (
            virtual_left
            + virtual_width
        )
        bottom = (
            virtual_top
            + virtual_height
        )

        if (
            x < virtual_left
            or x >= right
            or y < virtual_top
            or y >= bottom
        ):
            return ToolResult(
                success=False,
                error=(
                    f"Coordinate fuori dallo schermo "
                    f"(desktop virtuale): ({x}, {y}). Area: "
                    f"x={virtual_left}..{right - 1}, "
                    f"y={virtual_top}..{bottom - 1}."
                ),
            )

        set_cursor_pos = user32.SetCursorPos
        if hasattr(set_cursor_pos, "argtypes"):
            set_cursor_pos.argtypes = [
                wintypes.INT,
                wintypes.INT,
            ]
        if hasattr(set_cursor_pos, "restype"):
            set_cursor_pos.restype = wintypes.BOOL

        mouse_event = user32.mouse_event
        if hasattr(mouse_event, "argtypes"):
            mouse_event.argtypes = [
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_ulong,
            ]
        if hasattr(mouse_event, "restype"):
            mouse_event.restype = None

        try:
            moved = set_cursor_pos(
                x,
                y,
            )

            if not moved:
                return ToolResult(
                    success=False,
                    error=(
                        "Windows non ha consentito "
                        "di spostare il cursore."
                    ),
                )

            if self.click_delay_seconds > 0:
                time.sleep(
                    self.click_delay_seconds
                )

            mouse_event(
                MOUSEEVENTF_LEFTDOWN,
                0,
                0,
                0,
                0,
            )

            mouse_event(
                MOUSEEVENTF_LEFTUP,
                0,
                0,
                0,
                0,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile eseguire il click: {error}"
                ),
            )

        return ToolResult(
            success=True,
            output={
                "x": x,
                "y": y,
                "virtual_screen": {
                    "left": virtual_left,
                    "top": virtual_top,
                    "width": virtual_width,
                    "height": virtual_height,
                },
                "button": "left",
            },
        )




class MoveMouseTool(Tool):
    """
    Sposta il cursore del mouse a coordinate valide e verifica
    la posizione finale.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="move_mouse",
            description=(
                "Sposta il cursore del mouse a una coordinata "
                "dello schermo e verifica che Windows abbia "
                "raggiunto la posizione richiesta."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": (
                            "Coordinata orizzontale dello schermo."
                        ),
                    },
                    "y": {
                        "type": "integer",
                        "description": (
                            "Coordinata verticale dello schermo."
                        ),
                    },
                },
                "required": [
                    "x",
                    "y",
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
        x = arguments.get("x")
        y = arguments.get("y")

        if isinstance(x, bool) or not isinstance(x, int):
            return ToolResult(
                success=False,
                error="La coordinata 'x' deve essere un intero.",
            )

        if isinstance(y, bool) or not isinstance(y, int):
            return ToolResult(
                success=False,
                error="La coordinata 'y' deve essere un intero.",
            )

        if not hasattr(ctypes, "windll"):
            return ToolResult(
                success=False,
                error=(
                    "Il controllo del mouse è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        try:
            get_metrics = user32.GetSystemMetrics
            if hasattr(get_metrics, "argtypes"):
                get_metrics.argtypes = [
                    ctypes.c_int,
                ]
            if hasattr(get_metrics, "restype"):
                get_metrics.restype = ctypes.c_int

            (
                virtual_left,
                virtual_top,
                virtual_width,
                virtual_height,
            ) = _virtual_screen_bounds(
                user32
            )

            right = (
                virtual_left
                + virtual_width
            )
            bottom = (
                virtual_top
                + virtual_height
            )

            if (
                x < virtual_left
                or x >= right
                or y < virtual_top
                or y >= bottom
            ):
                return ToolResult(
                    success=False,
                    error=(
                        f"Coordinate fuori dallo schermo (desktop virtuale): "
                        f"({x}, {y}). Area: "
                        f"x={virtual_left}..{right - 1}, "
                        f"y={virtual_top}..{bottom - 1}."
                    ),
                )

            set_cursor_pos = user32.SetCursorPos
            if hasattr(set_cursor_pos, "argtypes"):
                set_cursor_pos.argtypes = [
                    wintypes.INT,
                    wintypes.INT,
                ]
            if hasattr(set_cursor_pos, "restype"):
                set_cursor_pos.restype = wintypes.BOOL

            if not set_cursor_pos(x, y):
                return ToolResult(
                    success=False,
                    error=(
                        "Windows non ha consentito "
                        "di spostare il cursore."
                    ),
                )

            get_cursor_pos = user32.GetCursorPos
            if hasattr(get_cursor_pos, "argtypes"):
                get_cursor_pos.argtypes = [
                    ctypes.POINTER(wintypes.POINT),
                ]
            if hasattr(get_cursor_pos, "restype"):
                get_cursor_pos.restype = wintypes.BOOL

            point = wintypes.POINT()

            if not get_cursor_pos(
                ctypes.byref(point)
            ):
                return ToolResult(
                    success=False,
                    error=(
                        "Il cursore è stato spostato, "
                        "ma non è stato possibile verificare "
                        "la posizione finale."
                    ),
                )

            verified = (
                int(point.x) == x
                and int(point.y) == y
            )

            if not verified:
                return ToolResult(
                    success=False,
                    output={
                        "requested_x": x,
                        "requested_y": y,
                        "actual_x": int(point.x),
                        "actual_y": int(point.y),
                    },
                    error=(
                        "La posizione finale del cursore "
                        "non corrisponde a quella richiesta."
                    ),
                )

            return ToolResult(
                success=True,
                output={
                    "x": x,
                    "y": y,
                    "verified": True,
                    "virtual_screen": {
                        "left": virtual_left,
                        "top": virtual_top,
                        "width": virtual_width,
                        "height": virtual_height,
                    },
                },
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile spostare il cursore: {error}"
                ),
            )


__all__ = [
    "ClickMouseTool",
    "MoveMouseTool",
]
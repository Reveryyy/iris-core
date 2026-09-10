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
                        "minimum": 0,
                    },
                    "y": {
                        "type": "integer",
                        "description": (
                            "Coordinata verticale del click."
                        ),
                        "minimum": 0,
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

        if x < 0 or y < 0:
            return ToolResult(
                success=False,
                error=(
                    "Le coordinate del mouse non possono essere negative."
                ),
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

        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)

        if screen_width <= 0 or screen_height <= 0:
            return ToolResult(
                success=False,
                error=(
                    "Impossibile determinare la risoluzione "
                    "dello schermo."
                ),
            )

        if x >= screen_width or y >= screen_height:
            return ToolResult(
                success=False,
                error=(
                    f"Coordinate fuori dallo schermo: "
                    f"({x}, {y}). Risoluzione: "
                    f"{screen_width}x{screen_height}."
                ),
            )

        set_cursor_pos = user32.SetCursorPos
        set_cursor_pos.argtypes = [
            wintypes.INT,
            wintypes.INT,
        ]
        set_cursor_pos.restype = wintypes.BOOL

        mouse_event = user32.mouse_event
        mouse_event.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_ulong,
        ]
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
                "screen_width": screen_width,
                "screen_height": screen_height,
                "button": "left",
            },
        )


__all__ = [
    "ClickMouseTool",
]
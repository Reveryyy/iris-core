from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class GetForegroundWindowTool(Tool):
    """
    Restituisce informazioni sulla finestra attualmente in primo piano.
    """

    def __init__(self) -> None:

        self._definition = ToolDefinition(
            name="get_foreground_window",
            description=(
                "Restituisce il titolo e l'handle della finestra "
                "attualmente in primo piano."
            ),
            input_schema={
                "type": "object",
                "properties": {},
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

        if arguments:
            return ToolResult(
                success=False,
                error=(
                    "Il tool get_foreground_window "
                    "non accetta argomenti."
                ),
            )

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il controllo delle finestre è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        get_foreground_window = (
            user32.GetForegroundWindow
        )

        get_foreground_window.argtypes = []
        get_foreground_window.restype = wintypes.HWND

        get_window_text_length = (
            user32.GetWindowTextLengthW
        )

        get_window_text_length.argtypes = [
            wintypes.HWND,
        ]
        get_window_text_length.restype = ctypes.c_int

        get_window_text = user32.GetWindowTextW

        get_window_text.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        get_window_text.restype = ctypes.c_int

        hwnd = get_foreground_window()

        if not hwnd:
            return ToolResult(
                success=False,
                error=(
                    "Windows non ha restituito "
                    "una finestra in primo piano."
                ),
            )

        length = get_window_text_length(
            hwnd
        )

        title = ""

        if length > 0:
            buffer = ctypes.create_unicode_buffer(
                length + 1
            )

            get_window_text(
                hwnd,
                buffer,
                length + 1,
            )

            title = buffer.value

        return ToolResult(
            success=True,
            output={
                "hwnd": int(hwnd),
                "title": title,
                "visible": bool(
                    user32.IsWindowVisible(hwnd)
                ),
            },
        )


__all__ = [
    "GetForegroundWindowTool",
]
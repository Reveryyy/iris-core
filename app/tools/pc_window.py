from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class FocusWindowTool(Tool):
    """
    Porta in primo piano una finestra visibile del desktop.

    La ricerca viene effettuata per titolo della finestra.
    Il tool non accetta HWND arbitrari dal modello.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="focus_window",
            description=(
                "Porta in primo piano una finestra visibile "
                "cercandola tramite il titolo."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "Titolo, o parte del titolo, della "
                            "finestra da portare in primo piano."
                        ),
                    },
                },
                "required": [
                    "title",
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

        title = arguments.get("title")

        if not isinstance(title, str):
            return ToolResult(
                success=False,
                error="Il titolo deve essere una stringa.",
            )

        title = title.strip()

        if not title:
            return ToolResult(
                success=False,
                error="Il titolo non può essere vuoto.",
            )

        if not hasattr(ctypes, "windll"):
            return ToolResult(
                success=False,
                error=(
                    "Il controllo delle finestre è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        matched_window: int | None = None
        matched_title: str | None = None

        enum_windows_proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def enum_windows_proc(
            hwnd: wintypes.HWND,
            _: wintypes.LPARAM,
        ) -> bool:

            nonlocal matched_window
            nonlocal matched_title

            if not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)

            if length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(
                length + 1
            )

            user32.GetWindowTextW(
                hwnd,
                buffer,
                length + 1,
            )

            window_title = buffer.value.strip()

            if not window_title:
                return True

            if title.lower() not in window_title.lower():
                return True

            matched_window = int(hwnd)
            matched_title = window_title

            return False

        callback = enum_windows_proc_type(
            enum_windows_proc
        )

        user32.EnumWindows(
            callback,
            0,
        )

        if matched_window is None:
            return ToolResult(
                success=False,
                error=(
                    f"Nessuna finestra visibile trovata "
                    f"per '{title}'."
                ),
            )

        SW_RESTORE = 9

        try:
            user32.ShowWindow(
                matched_window,
                SW_RESTORE,
            )

            foreground_result = user32.SetForegroundWindow(
                matched_window
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile controllare la finestra: {error}"
                ),
            )

        if not foreground_result:
            return ToolResult(
                success=False,
                error=(
                    f"La finestra '{matched_title}' è stata trovata "
                    "ma Windows non ha consentito di portarla "
                    "in primo piano."
                ),
            )

        return ToolResult(
            success=True,
            output={
                "title": matched_title,
                "hwnd": matched_window,
            },
        )


__all__ = [
    "FocusWindowTool",
]
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class TypeTextTool(Tool):
    """
    Inserisce testo Unicode nella finestra attualmente in primo piano
    utilizzando keybd_event di Windows.
    """

    def __init__(
        self,
        max_characters: int = 5_000,
        interval_seconds: float = 0.005,
    ) -> None:

        self.max_characters = max_characters
        self.interval_seconds = interval_seconds

        self._definition = ToolDefinition(
            name="type_text",
            description=(
                "Inserisce testo Unicode nella finestra "
                "attualmente in primo piano."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "Testo da digitare nella finestra "
                            "attualmente in primo piano."
                        ),
                    },
                },
                "required": [
                    "text",
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

        text = arguments.get(
            "text"
        )

        if not isinstance(
            text,
            str,
        ):
            return ToolResult(
                success=False,
                error="Il testo deve essere una stringa.",
            )

        if not text:
            return ToolResult(
                success=False,
                error="Il testo non può essere vuoto.",
            )

        if len(text) > self.max_characters:
            return ToolResult(
                success=False,
                error=(
                    f"Il testo supera il limite di "
                    f"{self.max_characters} caratteri."
                ),
            )

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "L'inserimento di testo è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        get_foreground_window = user32.GetForegroundWindow
        get_foreground_window.argtypes = []
        get_foreground_window.restype = wintypes.HWND

        keybd_event = user32.keybd_event
        keybd_event.argtypes = [
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            ctypes.c_ulong,
        ]
        keybd_event.restype = None

        foreground_window = get_foreground_window()

        if not foreground_window:
            return ToolResult(
                success=False,
                error=(
                    "Non è presente una finestra "
                    "in primo piano."
                ),
            )

        sent_characters = 0

        try:
            encoded = text.encode(
                "utf-16-le"
            )

            for index in range(
                0,
                len(encoded),
                2,
            ):
                code_unit = int.from_bytes(
                    encoded[
                        index:index + 2
                    ],
                    byteorder="little",
                )

                keybd_event(
                    0,
                    code_unit,
                    KEYEVENTF_UNICODE,
                    0,
                )

                keybd_event(
                    0,
                    code_unit,
                    KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    0,
                )

                sent_characters += 1

                if self.interval_seconds > 0:
                    time.sleep(
                        self.interval_seconds
                    )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile inviare il testo: {error}"
                ),
            )

        return ToolResult(
            success=True,
            output={
                "window_handle": int(
                    foreground_window
                ),
                "characters": sent_characters,
            },
        )


__all__ = [
    "TypeTextTool",
]
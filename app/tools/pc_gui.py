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

INPUT_KEYBOARD = 1


ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        (
            "wVk",
            wintypes.WORD,
        ),
        (
            "wScan",
            wintypes.WORD,
        ),
        (
            "dwFlags",
            wintypes.DWORD,
        ),
        (
            "time",
            wintypes.DWORD,
        ),
        (
            "dwExtraInfo",
            ULONG_PTR,
        ),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        (
            "dx",
            wintypes.LONG,
        ),
        (
            "dy",
            wintypes.LONG,
        ),
        (
            "mouseData",
            wintypes.DWORD,
        ),
        (
            "dwFlags",
            wintypes.DWORD,
        ),
        (
            "time",
            wintypes.DWORD,
        ),
        (
            "dwExtraInfo",
            ULONG_PTR,
        ),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        (
            "uMsg",
            wintypes.DWORD,
        ),
        (
            "wParamL",
            wintypes.WORD,
        ),
        (
            "wParamH",
            wintypes.WORD,
        ),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        (
            "ki",
            KEYBDINPUT,
        ),
        (
            "mi",
            MOUSEINPUT,
        ),
        (
            "hi",
            HARDWAREINPUT,
        ),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = (
        "u",
    )

    _fields_ = [
        (
            "type",
            wintypes.DWORD,
        ),
        (
            "u",
            INPUT_UNION,
        ),
    ]


class TypeTextTool(Tool):
    """
    Inserisce testo Unicode nella finestra attualmente in primo piano
    utilizzando SendInput di Windows.
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

        get_foreground_window = (
            user32.GetForegroundWindow
        )

        if hasattr(
            get_foreground_window,
            "argtypes",
        ):
            get_foreground_window.argtypes = []

        if hasattr(
            get_foreground_window,
            "restype",
        ):
            get_foreground_window.restype = (
                wintypes.HWND
            )

        send_input = user32.SendInput

        if hasattr(
            send_input,
            "argtypes",
        ):
            send_input.argtypes = [
                wintypes.UINT,
                ctypes.POINTER(INPUT),
                ctypes.c_int,
            ]

        if hasattr(
            send_input,
            "restype",
        ):
            send_input.restype = wintypes.UINT

        foreground_window = (
            get_foreground_window()
        )

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

                key_down = INPUT(
                    type=INPUT_KEYBOARD,
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=code_unit,
                        dwFlags=KEYEVENTF_UNICODE,
                        time=0,
                        dwExtraInfo=0,
                    ),
                )

                key_up = INPUT(
                    type=INPUT_KEYBOARD,
                    ki=KEYBDINPUT(
                        wVk=0,
                        wScan=code_unit,
                        dwFlags=(
                            KEYEVENTF_UNICODE
                            | KEYEVENTF_KEYUP
                        ),
                        time=0,
                        dwExtraInfo=0,
                    ),
                )

                inputs = (
                    INPUT * 2
                )(
                    key_down,
                    key_up,
                )

                sent = send_input(
                    2,
                    inputs,
                    ctypes.sizeof(INPUT),
                )

                if int(sent) != 2:
                    error_code = ctypes.get_last_error()

                    if error_code:
                        return ToolResult(
                            success=False,
                            error=(
                                "Impossibile inviare il testo: "
                                f"SendInput ha restituito "
                                f"{sent}/2 eventi "
                                f"(errore Windows "
                                f"{error_code})."
                            ),
                        )

                    return ToolResult(
                        success=False,
                        error=(
                            "Impossibile inviare il testo: "
                            f"SendInput ha restituito "
                            f"{sent}/2 eventi."
                        ),
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
    "KEYEVENTF_KEYUP",
    "KEYEVENTF_UNICODE",
    "INPUT_KEYBOARD",
    "KEYBDINPUT",
    "MOUSEINPUT",
    "HARDWAREINPUT",
    "INPUT_UNION",
    "INPUT",
    "TypeTextTool",
]
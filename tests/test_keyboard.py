from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


KEYEVENTF_KEYUP = 0x0002


class PressKeyTool(Tool):
    """
    Esegue un tasto o una combinazione di tasti autorizzata
    nella finestra attualmente in primo piano.
    """

    ALLOWED_KEYS = {
        "ENTER": 0x0D,
        "ESC": 0x1B,
        "TAB": 0x09,
        "SPACE": 0x20,
        "BACKSPACE": 0x08,
        "DELETE": 0x2E,
        "INSERT": 0x2D,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "UP": 0x26,
        "DOWN": 0x28,
        "LEFT": 0x25,
        "RIGHT": 0x27,
        "F1": 0x70,
        "F2": 0x71,
        "F3": 0x72,
        "F4": 0x73,
        "F5": 0x74,
        "F6": 0x75,
        "F7": 0x76,
        "F8": 0x77,
        "F9": 0x78,
        "F10": 0x79,
        "F11": 0x7A,
        "F12": 0x7B,
        "A": 0x41,
        "B": 0x42,
        "C": 0x43,
        "D": 0x44,
        "E": 0x45,
        "F": 0x46,
        "G": 0x47,
        "H": 0x48,
        "I": 0x49,
        "J": 0x4A,
        "K": 0x4B,
        "L": 0x4C,
        "M": 0x4D,
        "N": 0x4E,
        "O": 0x4F,
        "P": 0x50,
        "Q": 0x51,
        "R": 0x52,
        "S": 0x53,
        "T": 0x54,
        "U": 0x55,
        "V": 0x56,
        "W": 0x57,
        "X": 0x58,
        "Y": 0x59,
        "Z": 0x5A,
        "0": 0x30,
        "1": 0x31,
        "2": 0x32,
        "3": 0x33,
        "4": 0x34,
        "5": 0x35,
        "6": 0x36,
        "7": 0x37,
        "8": 0x38,
        "9": 0x39,
        "CTRL": 0x11,
        "SHIFT": 0x10,
        "ALT": 0x12,
        "WIN": 0x5B,
    }

    ALLOWED_COMBINATIONS = {
        "CTRL+A",
        "CTRL+C",
        "CTRL+V",
        "CTRL+X",
        "CTRL+Z",
        "CTRL+S",
        "CTRL+F",
        "CTRL+W",
        "ALT+F4",
        "ALT+TAB",
        "SHIFT+TAB",
    }

    def __init__(
        self,
        key_delay_seconds: float = 0.05,
    ) -> None:

        self.key_delay_seconds = key_delay_seconds

        self._definition = ToolDefinition(
            name="press_key",
            description=(
                "Preme un tasto o una combinazione di tasti "
                "autorizzata nella finestra attualmente in primo piano."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Tasto o combinazione autorizzata, "
                            "ad esempio ENTER o CTRL+C."
                        ),
                    },
                },
                "required": [
                    "key",
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

        key = arguments.get("key")

        if not isinstance(key, str):
            return ToolResult(
                success=False,
                error="Il tasto deve essere una stringa.",
            )

        key = self._normalize_key(
            key
        )

        if not key:
            return ToolResult(
                success=False,
                error="Il tasto non può essere vuoto.",
            )

        if "+" in key:
            if key in self.ALLOWED_COMBINATIONS:
                return self._press_combination(
                    key
                )

            return ToolResult(
                success=False,
                error=(
                    f"La combinazione '{key}' "
                    "non è presente nella allowlist."
                ),
            )

        if key not in self.ALLOWED_KEYS:
            return ToolResult(
                success=False,
                error=(
                    f"Il tasto '{key}' non è presente "
                    "nella allowlist."
                ),
            )

        return self._press_single_key(
            key
        )

    @staticmethod
    def _normalize_key(
        key: str,
    ) -> str:
        key = key.strip().upper()

        if not key:
            return ""

        if "+" not in key:
            return key

        parts = [
            part.strip()
            for part in key.split("+")
        ]

        if any(
            not part
            for part in parts
        ):
            return ""

        return "+".join(
            parts
        )

    def _get_foreground_window(
        self,
    ) -> int | None:

        user32 = ctypes.windll.user32

        get_foreground_window = (
            user32.GetForegroundWindow
        )

        get_foreground_window.argtypes = []
        get_foreground_window.restype = wintypes.HWND

        hwnd = get_foreground_window()

        if not hwnd:
            return None

        return int(hwnd)

    def _keybd_event(
        self,
        virtual_key: int,
        flags: int = 0,
    ) -> None:

        user32 = ctypes.windll.user32

        keybd_event = user32.keybd_event

        keybd_event.argtypes = [
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            ctypes.c_ulong,
        ]

        keybd_event.restype = None

        keybd_event(
            virtual_key,
            0,
            flags,
            0,
        )

    def _press_single_key(
        self,
        key: str,
    ) -> ToolResult:

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il controllo della tastiera è disponibile "
                    "solo su Windows."
                ),
            )

        hwnd = self._get_foreground_window()

        if hwnd is None:
            return ToolResult(
                success=False,
                error=(
                    "Non è presente una finestra "
                    "in primo piano."
                ),
            )

        virtual_key = self.ALLOWED_KEYS[key]

        try:
            self._keybd_event(
                virtual_key
            )

            self._keybd_event(
                virtual_key,
                KEYEVENTF_KEYUP,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile premere '{key}': {error}"
                ),
            )

        if self.key_delay_seconds > 0:
            time.sleep(
                self.key_delay_seconds
            )

        return ToolResult(
            success=True,
            output={
                "key": key,
                "window_handle": hwnd,
                "combination": False,
            },
        )

    def _press_combination(
        self,
        combination: str,
    ) -> ToolResult:

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il controllo della tastiera è disponibile "
                    "solo su Windows."
                ),
            )

        hwnd = self._get_foreground_window()

        if hwnd is None:
            return ToolResult(
                success=False,
                error=(
                    "Non è presente una finestra "
                    "in primo piano."
                ),
            )

        parts = [
            part.strip()
            for part in combination.split("+")
        ]

        if len(parts) < 2:
            return ToolResult(
                success=False,
                error=(
                    f"Combinazione non valida: {combination}"
                ),
            )

        virtual_keys: list[tuple[str, int]] = []

        for part in parts:
            virtual_key = self.ALLOWED_KEYS.get(
                part
            )

            if virtual_key is None:
                return ToolResult(
                    success=False,
                    error=(
                        f"Il tasto '{part}' non è "
                        "presente nella allowlist."
                    ),
                )

            virtual_keys.append(
                (
                    part,
                    virtual_key,
                )
            )

        try:
            for _, virtual_key in virtual_keys:
                self._keybd_event(
                    virtual_key
                )

            for _, virtual_key in reversed(
                virtual_keys
            ):
                self._keybd_event(
                    virtual_key,
                    KEYEVENTF_KEYUP,
                )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile eseguire '{combination}': "
                    f"{error}"
                ),
            )

        if self.key_delay_seconds > 0:
            time.sleep(
                self.key_delay_seconds
            )

        return ToolResult(
            success=True,
            output={
                "key": combination,
                "window_handle": hwnd,
                "combination": True,
            },
        )


__all__ = [
    "PressKeyTool",
]
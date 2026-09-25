from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class ListWindowsTool(Tool):
    """
    Elenca le finestre top-level visibili rilevate dal desktop Windows.
    """

    SEARCH_TIMEOUT_SECONDS = 3.0
    SEARCH_INTERVAL_SECONDS = 0.10

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="list_windows",
            description=(
                "Elenca dinamicamente le finestre top-level visibili del "
                "desktop Windows, includendo titolo, handle, processo, "
                "classe, stato minimized e finestra foreground."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset(
                {
                    Permission.READ.value,
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
                error="list_windows non accetta argomenti.",
            )

        if not hasattr(ctypes, "windll"):
            return ToolResult(
                success=False,
                error=(
                    "La discovery delle finestre è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32

        self._configure_api(user32)

        try:
            windows = self._discover(user32)
        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile scoprire le finestre: {error}"
                ),
            )

        return ToolResult(
            success=True,
            output={
                "count": len(windows),
                "windows": windows,
                "user_message": (
                    f"Ho rilevato {len(windows)} finestre visibili "
                    "sul desktop."
                ),
            },
        )

    @staticmethod
    def _configure_api(
        user32: Any,
    ) -> None:
        for name in (
            "EnumWindows",
            "IsWindowVisible",
            "IsIconic",
            "GetWindowTextLengthW",
            "GetWindowTextW",
            "GetClassNameW",
            "GetForegroundWindow",
            "GetWindowThreadProcessId",
        ):
            if not hasattr(user32, name):
                raise OSError(
                    f"Windows API mancante: {name}"
                )

        user32.IsWindowVisible.argtypes = [
            wintypes.HWND,
        ]
        user32.IsWindowVisible.restype = wintypes.BOOL

        user32.IsIconic.argtypes = [
            wintypes.HWND,
        ]
        user32.IsIconic.restype = wintypes.BOOL

        user32.GetWindowTextLengthW.argtypes = [
            wintypes.HWND,
        ]
        user32.GetWindowTextLengthW.restype = ctypes.c_int

        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetWindowTextW.restype = ctypes.c_int

        user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int

        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND

        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    @staticmethod
    def _discover(
        user32: Any,
    ) -> list[dict[str, Any]]:
        foreground = int(
            user32.GetForegroundWindow() or 0
        )

        windows: list[dict[str, Any]] = []

        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def callback(
            hwnd: wintypes.HWND,
            _lparam: wintypes.LPARAM,
        ) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            title = ListWindowsTool._get_window_text(
                user32,
                hwnd,
            )

            window_class = (
                ListWindowsTool._get_window_class(
                    user32,
                    hwnd,
                )
            )

            process_id = wintypes.DWORD()

            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )

            windows.append(
                {
                    "hwnd": int(hwnd),
                    "title": title,
                    "window_class": window_class,
                    "pid": int(process_id.value),
                    "minimized": bool(
                        user32.IsIconic(hwnd)
                    ),
                    "foreground": int(hwnd) == foreground,
                }
            )

            return True

        callback_instance = callback_type(
            callback
        )

        if not user32.EnumWindows(
            callback_instance,
            0,
        ):
            raise OSError(
                "EnumWindows ha restituito un errore."
            )

        windows.sort(
            key=lambda item: (
                not item["foreground"],
                item["title"].casefold(),
                item["hwnd"],
            )
        )

        return windows

    @staticmethod
    def _get_window_text(
        user32: Any,
        hwnd: wintypes.HWND,
    ) -> str:
        length = user32.GetWindowTextLengthW(
            hwnd
        )

        if length <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(
            length + 1
        )

        user32.GetWindowTextW(
            hwnd,
            buffer,
            length + 1,
        )

        return buffer.value.strip()

    @staticmethod
    def _get_window_class(
        user32: Any,
        hwnd: wintypes.HWND,
    ) -> str:
        buffer = ctypes.create_unicode_buffer(
            512
        )

        result = user32.GetClassNameW(
            hwnd,
            buffer,
            len(buffer),
        )

        if result <= 0:
            return ""

        return buffer.value.strip()


__all__ = [
    "ListWindowsTool",
]

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


CF_UNICODETEXT = 13

GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040


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


class GetClipboardTool(Tool):
    """
    Legge il contenuto testuale corrente degli appunti di Windows.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="get_clipboard",
            description=(
                "Legge il contenuto testuale corrente "
                "degli appunti di Windows."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            risk_level="medium",
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
        if not isinstance(
            arguments,
            dict,
        ):
            return ToolResult(
                success=False,
                error=(
                    "Gli argomenti devono essere "
                    "un dizionario."
                ),
            )

        if arguments:
            return ToolResult(
                success=False,
                error=(
                    "get_clipboard non accetta argomenti."
                ),
            )

        if not hasattr(
            ctypes,
            "windll",
        ):
            return ToolResult(
                success=False,
                error=(
                    "La lettura degli appunti è disponibile "
                    "solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        open_clipboard = (
            user32.OpenClipboard
        )
        close_clipboard = (
            user32.CloseClipboard
        )
        is_format_available = (
            user32.IsClipboardFormatAvailable
        )
        get_clipboard_data = (
            user32.GetClipboardData
        )

        global_lock = (
            kernel32.GlobalLock
        )
        global_unlock = (
            kernel32.GlobalUnlock
        )

        _configure_function(
            open_clipboard,
            [
                wintypes.HWND,
            ],
            wintypes.BOOL,
        )

        _configure_function(
            close_clipboard,
            [],
            wintypes.BOOL,
        )

        _configure_function(
            is_format_available,
            [
                wintypes.UINT,
            ],
            wintypes.BOOL,
        )

        _configure_function(
            get_clipboard_data,
            [
                wintypes.UINT,
            ],
            wintypes.HANDLE,
        )

        _configure_function(
            global_lock,
            [
                wintypes.HGLOBAL,
            ],
            wintypes.LPVOID,
        )

        _configure_function(
            global_unlock,
            [
                wintypes.HGLOBAL,
            ],
            wintypes.BOOL,
        )

        opened = False
        locked_handle = None

        try:
            if not open_clipboard(None):
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile aprire gli appunti "
                        "di Windows."
                    ),
                )

            opened = True

            if not is_format_available(
                CF_UNICODETEXT
            ):
                return ToolResult(
                    success=False,
                    error=(
                        "Gli appunti non contengono "
                        "testo Unicode."
                    ),
                )

            handle = get_clipboard_data(
                CF_UNICODETEXT
            )

            if not handle:
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile recuperare il testo "
                        "dagli appunti."
                    ),
                )

            locked_handle = global_lock(
                handle
            )

            if not locked_handle:
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile accedere al testo "
                        "degli appunti."
                    ),
                )

            text = ctypes.wstring_at(
                locked_handle
            )

            return ToolResult(
                success=True,
                output={
                    "text": text,
                    "characters": len(text),
                },
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile leggere gli appunti: "
                    f"{error}"
                ),
            )

        finally:
            if locked_handle:
                global_unlock(
                    locked_handle
                )

            if opened:
                close_clipboard()


class SetClipboardTool(Tool):
    """
    Scrive testo Unicode negli appunti di Windows.
    """

    def __init__(
        self,
        max_characters: int = 10_000,
    ) -> None:
        self.max_characters = (
            max_characters
        )

        self._definition = ToolDefinition(
            name="set_clipboard",
            description=(
                "Scrive testo Unicode negli appunti "
                "di Windows."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "Testo da mettere negli appunti."
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
                    Permission.WRITE.value,
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
        if not isinstance(
            arguments,
            dict,
        ):
            return ToolResult(
                success=False,
                error=(
                    "Gli argomenti devono essere "
                    "un dizionario."
                ),
            )

        text = arguments.get(
            "text"
        )

        if not isinstance(
            text,
            str,
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il testo deve essere una stringa."
                ),
            )

        if not text:
            return ToolResult(
                success=False,
                error=(
                    "Il testo non può essere vuoto."
                ),
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
                    "La scrittura degli appunti è "
                    "disponibile solo su Windows."
                ),
            )

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        open_clipboard = (
            user32.OpenClipboard
        )
        close_clipboard = (
            user32.CloseClipboard
        )
        empty_clipboard = (
            user32.EmptyClipboard
        )
        set_clipboard_data = (
            user32.SetClipboardData
        )

        global_alloc = (
            kernel32.GlobalAlloc
        )
        global_lock = (
            kernel32.GlobalLock
        )
        global_unlock = (
            kernel32.GlobalUnlock
        )
        global_free = (
            kernel32.GlobalFree
        )

        _configure_function(
            open_clipboard,
            [
                wintypes.HWND,
            ],
            wintypes.BOOL,
        )

        _configure_function(
            close_clipboard,
            [],
            wintypes.BOOL,
        )

        _configure_function(
            empty_clipboard,
            [],
            wintypes.BOOL,
        )

        _configure_function(
            set_clipboard_data,
            [
                wintypes.UINT,
                wintypes.HANDLE,
            ],
            wintypes.HANDLE,
        )

        _configure_function(
            global_alloc,
            [
                wintypes.UINT,
                ctypes.c_size_t,
            ],
            wintypes.HGLOBAL,
        )

        _configure_function(
            global_lock,
            [
                wintypes.HGLOBAL,
            ],
            wintypes.LPVOID,
        )

        _configure_function(
            global_unlock,
            [
                wintypes.HGLOBAL,
            ],
            wintypes.BOOL,
        )

        _configure_function(
            global_free,
            [
                wintypes.HGLOBAL,
            ],
            wintypes.HGLOBAL,
        )

        encoded = (
            text + "\0"
        ).encode(
            "utf-16-le"
        )

        memory_handle = None
        locked_handle = None
        opened = False
        transferred = False

        try:
            if not open_clipboard(None):
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile aprire gli appunti "
                        "di Windows."
                    ),
                )

            opened = True

            memory_handle = global_alloc(
                GMEM_MOVEABLE | GMEM_ZEROINIT,
                len(encoded),
            )

            if not memory_handle:
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile allocare la memoria "
                        "necessaria per gli appunti."
                    ),
                )

            locked_handle = global_lock(
                memory_handle
            )

            if not locked_handle:
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile accedere alla memoria "
                        "degli appunti."
                    ),
                )

            ctypes.memmove(
                locked_handle,
                encoded,
                len(encoded),
            )

            global_unlock(
                memory_handle
            )

            locked_handle = None

            if not empty_clipboard():
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile svuotare gli appunti "
                        "di Windows."
                    ),
                )

            result_handle = set_clipboard_data(
                CF_UNICODETEXT,
                memory_handle,
            )

            if not result_handle:
                return ToolResult(
                    success=False,
                    error=(
                        "Impossibile salvare il testo "
                        "negli appunti di Windows."
                    ),
                )

            transferred = True
            memory_handle = None

            return ToolResult(
                success=True,
                output={
                    "characters": len(text),
                },
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile scrivere negli appunti: "
                    f"{error}"
                ),
            )

        finally:
            if locked_handle:
                global_unlock(
                    locked_handle
                )

            if (
                memory_handle
                and not transferred
            ):
                global_free(
                    memory_handle
                )

            if opened:
                close_clipboard()


__all__ = [
    "CF_UNICODETEXT",
    "GMEM_MOVEABLE",
    "GMEM_ZEROINIT",
    "GetClipboardTool",
    "SetClipboardTool",
]
from __future__ import annotations

import ctypes
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class FocusWindowTool(Tool):
    """
    Porta in primo piano una finestra visibile del desktop.

    La ricerca viene effettuata principalmente tramite il titolo,
    ma usa anche nome del processo e classe della finestra come
    fallback. Questo è particolarmente utile con applicazioni
    moderne di Windows, come il nuovo Blocco note.

    Il tool non accetta HWND arbitrari dal modello.
    """

    SEARCH_TIMEOUT_SECONDS = 3.0
    SEARCH_INTERVAL_SECONDS = 0.10

    TITLE_ALIASES: dict[str, tuple[str, ...]] = {
        "blocco note": (
            "blocco note",
            "notepad",
        ),
        "notepad": (
            "notepad",
            "blocco note",
        ),
        "editor di testo": (
            "editor di testo",
            "blocco note",
            "notepad",
        ),
        "calcolatrice": (
            "calcolatrice",
            "calculator",
        ),
        "calculator": (
            "calculator",
            "calcolatrice",
        ),
    }

    PROCESS_ALIASES: dict[str, tuple[str, ...]] = {
        "blocco note": (
            "notepad.exe",
            "notepad",
        ),
        "notepad": (
            "notepad.exe",
            "notepad",
        ),
        "editor di testo": (
            "notepad.exe",
            "notepad",
        ),
        "calcolatrice": (
            "calculator.exe",
            "calculator",
        ),
        "calculator": (
            "calculator.exe",
            "calculator",
        ),
    }

    WINDOW_CLASS_ALIASES: dict[str, tuple[str, ...]] = {
        "blocco note": (
            "notepad",
        ),
        "notepad": (
            "notepad",
        ),
        "editor di testo": (
            "notepad",
        ),
        "calcolatrice": (
            "applicationframewindow",
            "winui",
        ),
        "calculator": (
            "applicationframewindow",
            "winui",
        ),
    }

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="focus_window",
            description=(
                "Porta in primo piano una finestra visibile "
                "cercandola tramite titolo, processo o classe "
                "della finestra."
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

        title = arguments.get(
            "title"
        )

        if not isinstance(
            title,
            str,
        ):
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
        kernel32 = ctypes.windll.kernel32

        normalized_title = (
            self._normalize_text(
                title
            )
        )

        search_titles = (
            self._build_search_titles(
                normalized_title
            )
        )

        search_processes = (
            self._build_search_values(
                normalized_title,
                self.PROCESS_ALIASES,
            )
        )

        search_classes = (
            self._build_search_values(
                normalized_title,
                self.WINDOW_CLASS_ALIASES,
            )
        )

        deadline = (
            time.monotonic()
            + self.SEARCH_TIMEOUT_SECONDS
        )

        matched_window: int | None = None
        matched_title: str | None = None
        matched_process: str | None = None
        matched_class: str | None = None
        matched_reason: str | None = None

        enum_windows_proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        while time.monotonic() < deadline:

            matched_window = None
            matched_title = None
            matched_process = None
            matched_class = None
            matched_reason = None

            def enum_windows_proc(
                hwnd: wintypes.HWND,
                _: wintypes.LPARAM,
            ) -> bool:

                nonlocal matched_window
                nonlocal matched_title
                nonlocal matched_process
                nonlocal matched_class
                nonlocal matched_reason

                if not user32.IsWindowVisible(
                    hwnd
                ):
                    return True

                window_title = (
                    self._get_window_title(
                        user32,
                        hwnd,
                    )
                )

                window_class = (
                    self._get_window_class(
                        user32,
                        hwnd,
                    )
                )

                process_name = (
                    self._get_process_name(
                        kernel32,
                        user32,
                        hwnd,
                    )
                )

                normalized_window_title = (
                    self._normalize_text(
                        window_title
                    )
                )

                normalized_window_class = (
                    self._normalize_text(
                        window_class
                    )
                )

                normalized_process_name = (
                    self._normalize_text(
                        process_name
                    )
                )

                title_match = (
                    self._title_matches(
                        normalized_window_title,
                        search_titles,
                    )
                )

                process_match = (
                    self._value_matches(
                        normalized_process_name,
                        search_processes,
                    )
                )

                class_match = (
                    self._value_matches(
                        normalized_window_class,
                        search_classes,
                    )
                )

                if not (
                    title_match
                    or process_match
                    or class_match
                ):
                    return True

                matched_window = int(
                    hwnd
                )

                matched_title = (
                    window_title
                    or "<titolo non disponibile>"
                )

                matched_process = (
                    process_name
                    or "<processo non disponibile>"
                )

                matched_class = (
                    window_class
                    or "<classe non disponibile>"
                )

                if title_match:
                    matched_reason = "title"
                elif process_match:
                    matched_reason = "process"
                else:
                    matched_reason = "class"

                return False

            callback = (
                enum_windows_proc_type(
                    enum_windows_proc
                )
            )

            user32.EnumWindows(
                callback,
                0,
            )

            if matched_window is not None:
                break

            time.sleep(
                self.SEARCH_INTERVAL_SECONDS
            )

        if matched_window is None:
            searched_details = []

            if search_titles:
                searched_details.append(
                    "titolo"
                )

            if search_processes:
                searched_details.append(
                    "processo"
                )

            if search_classes:
                searched_details.append(
                    "classe"
                )

            details_text = (
                ", ".join(
                    searched_details
                )
                if searched_details
                else "titolo"
            )

            return ToolResult(
                success=False,
                error=(
                    f"Nessuna finestra visibile trovata "
                    f"per '{title}' entro "
                    f"{self.SEARCH_TIMEOUT_SECONDS:.1f} secondi "
                    f"(ricerca tramite {details_text})."
                ),
            )

        SW_RESTORE = 9

        try:
            user32.ShowWindow(
                matched_window,
                SW_RESTORE,
            )

            foreground_result = (
                user32.SetForegroundWindow(
                    matched_window
                )
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile controllare la finestra: "
                    f"{error}"
                ),
            )

        if not foreground_result:
            return ToolResult(
                success=False,
                error=(
                    f"La finestra '{matched_title}' è stata trovata "
                    f"(processo: {matched_process}, "
                    f"classe: {matched_class}), "
                    "ma Windows non ha consentito di portarla "
                    "in primo piano."
                ),
            )

        return ToolResult(
            success=True,
            output={
                "title": matched_title,
                "hwnd": matched_window,
                "process": matched_process,
                "window_class": matched_class,
                "matched_by": matched_reason,
            },
        )

    # ========================================================================
    # WINDOWS HELPERS
    # ========================================================================

    @staticmethod
    def _get_window_title(
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

    @staticmethod
    def _get_process_name(
        kernel32: Any,
        user32: Any,
        hwnd: wintypes.HWND,
    ) -> str:
        process_id = wintypes.DWORD()

        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(
                process_id
            ),
        )

        if not process_id.value:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        process_handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id.value,
        )

        if not process_handle:
            return ""

        try:
            buffer_length = wintypes.DWORD(
                32768
            )

            buffer = ctypes.create_unicode_buffer(
                buffer_length.value
            )

            result = (
                kernel32.QueryFullProcessImageNameW(
                    process_handle,
                    0,
                    buffer,
                    ctypes.byref(
                        buffer_length
                    ),
                )
            )

            if not result:
                return ""

            full_path = (
                buffer.value
            )

            return Path(
                full_path
            ).name

        finally:
            kernel32.CloseHandle(
                process_handle
            )

    # ========================================================================
    # MATCHING
    # ========================================================================

    @classmethod
    def _build_search_titles(
        cls,
        normalized_title: str,
    ) -> tuple[str, ...]:
        aliases = (
            cls.TITLE_ALIASES.get(
                normalized_title
            )
        )

        if aliases:
            return aliases

        return (
            normalized_title,
        )

    @classmethod
    def _build_search_values(
        cls,
        normalized_title: str,
        mapping: dict[str, tuple[str, ...]],
    ) -> tuple[str, ...]:
        aliases = (
            mapping.get(
                normalized_title
            )
        )

        if aliases:
            return tuple(
                cls._normalize_text(
                    alias
                )
                for alias in aliases
            )

        return (
            normalized_title,
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        normalized = (
            unicodedata.normalize(
                "NFKD",
                value,
            )
            .encode(
                "ascii",
                "ignore",
            )
            .decode(
                "ascii",
            )
            .lower()
        )

        normalized = (
            " ".join(
                normalized.split()
            )
        )

        return normalized.strip()

    @staticmethod
    def _title_matches(
        window_title: str,
        search_titles: tuple[str, ...],
    ) -> bool:
        if not window_title:
            return False

        for candidate in search_titles:
            if not candidate:
                continue

            if candidate in window_title:
                return True

        return False

    @staticmethod
    def _value_matches(
        value: str,
        candidates: tuple[str, ...],
    ) -> bool:
        if not value:
            return False

        for candidate in candidates:
            if not candidate:
                continue

            if value == candidate:
                return True

            if candidate in value:
                return True

            if value in candidate:
                return True

        return False


__all__ = [
    "FocusWindowTool",
]
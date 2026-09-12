from __future__ import annotations

import ctypes
import time
import unicodedata
from ctypes import wintypes
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class MinimizeWindowTool(Tool):
    """
    Minimizza una finestra visibile del desktop.

    La ricerca viene effettuata tramite titolo, con alias comuni
    per applicazioni Windows note.
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

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="minimize_window",
            description=(
                "Mette una finestra visibile in secondo piano "
                "minimizzandola, cercandola tramite titolo."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "Titolo, o parte del titolo, della "
                            "finestra da minimizzare."
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

        deadline = (
            time.monotonic()
            + self.SEARCH_TIMEOUT_SECONDS
        )

        matched_window: int | None = None
        matched_title: str | None = None

        enum_windows_proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        while time.monotonic() < deadline:

            matched_window = None
            matched_title = None

            def enum_windows_proc(
                hwnd: wintypes.HWND,
                _: wintypes.LPARAM,
            ) -> bool:

                nonlocal matched_window
                nonlocal matched_title

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

                if not window_title:
                    return True

                normalized_window_title = (
                    self._normalize_text(
                        window_title
                    )
                )

                if not self._title_matches(
                    normalized_window_title,
                    search_titles,
                ):
                    return True

                matched_window = int(
                    hwnd
                )

                matched_title = (
                    window_title
                )

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
            return ToolResult(
                success=False,
                error=(
                    f"Nessuna finestra visibile trovata "
                    f"per '{title}' entro "
                    f"{self.SEARCH_TIMEOUT_SECONDS:.1f} secondi."
                ),
            )

        SW_MINIMIZE = 6

        try:
            result = user32.ShowWindow(
                matched_window,
                SW_MINIMIZE,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile minimizzare la finestra: "
                    f"{error}"
                ),
            )

        if not result:
            # ShowWindow può restituire False anche quando l'azione
            # non deve essere interpretata automaticamente come errore.
            # Verifichiamo comunque lo stato della finestra.
            if user32.IsWindowVisible(
                matched_window
            ):
                return ToolResult(
                    success=False,
                    error=(
                        f"La finestra '{matched_title}' è stata trovata "
                        "ma Windows non ha consentito di minimizzarla."
                    ),
                )

        return ToolResult(
            success=True,
            output={
                "title": matched_title,
                "hwnd": matched_window,
                "state": "minimized",
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


__all__ = [
    "MinimizeWindowTool",
]
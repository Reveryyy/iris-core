from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from app.tools.application_resolver import (
    ApplicationResolver,
)
from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


# ============================================================================
# CLOSE APPLICATION
# ============================================================================

class CloseApplicationTool(Tool):
    """
    Cerca la finestra principale visibile di un'applicazione Windows,
    invia WM_CLOSE e verifica che la finestra sia stata realmente chiusa.

    L'applicazione viene identificata tramite ApplicationResolver e,
    durante la ricerca della finestra, vengono considerati:
    - titolo della finestra;
    - nome del processo;
    - classe della finestra;
    - nome dell'applicazione risolta;
    - nome dell'eseguibile risolto.

    Il tool usa WM_CLOSE invece di terminare forzatamente il processo.
    In questo modo l'applicazione può gestire normalmente eventuali
    richieste di salvataggio o altre procedure di chiusura.
    """

    SEARCH_TIMEOUT_SECONDS = 3.0
    SEARCH_INTERVAL_SECONDS = 0.10

    CLOSE_VERIFY_TIMEOUT_SECONDS = 5.0
    CLOSE_VERIFY_INTERVAL_SECONDS = 0.10

    WM_CLOSE = 0x0010

    def __init__(
        self,
        resolver: ApplicationResolver | None = None,
    ) -> None:
        self.resolver = (
            resolver
            or ApplicationResolver()
        )

        self._definition = ToolDefinition(
            name="close_application",
            description=(
                "Cerca la finestra principale visibile di "
                "un'applicazione presente sul PC, la chiude "
                "normalmente e verifica che sia stata realmente chiusa."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Nome dell'applicazione da chiudere."
                        ),
                    },
                },
                "required": [
                    "name",
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
    def definition(
        self,
    ) -> ToolDefinition:
        return self._definition

    # ========================================================================
    # EXECUTE
    # ========================================================================

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        name = arguments.get(
            "name"
        )

        if not isinstance(
            name,
            str,
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il nome dell'applicazione "
                    "deve essere una stringa."
                ),
            )

        name = name.strip()

        if not name:
            return ToolResult(
                success=False,
                error=(
                    "Il nome dell'applicazione "
                    "non può essere vuoto."
                ),
            )

        if os.name != "nt":
            return ToolResult(
                success=False,
                error=(
                    "La chiusura delle applicazioni "
                    "è disponibile solo su Windows."
                ),
            )

        # --------------------------------------------------------------------
        # APPLICATION DISCOVERY
        # --------------------------------------------------------------------

        try:
            application = self.resolver.resolve(
                name
            )

        except (
            OSError,
            ValueError,
            TypeError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    "Errore durante la ricerca "
                    f"dell'applicazione: {error}"
                ),
            )

        if application is None:
            return ToolResult(
                success=False,
                error=(
                    f"Non riesco a trovare "
                    f"l'applicazione '{name}' "
                    "sul PC."
                ),
            )

        # --------------------------------------------------------------------
        # WINDOWS API
        # --------------------------------------------------------------------

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._configure_windows_api(
            user32=user32,
            kernel32=kernel32,
        )

        expected_process_names = (
            self._expected_process_names(
                application
            )
        )

        normalized_query = (
            self._normalize_text(
                name
            )
        )

        # --------------------------------------------------------------------
        # WINDOW DISCOVERY
        # --------------------------------------------------------------------

        matched_window: dict[str, Any] | None = None

        deadline = (
            time.monotonic()
            + self.SEARCH_TIMEOUT_SECONDS
        )

        while time.monotonic() < deadline:
            matched_window = (
                self._find_best_window(
                    user32=user32,
                    kernel32=kernel32,
                    query=normalized_query,
                    expected_process_names=(
                        expected_process_names
                    ),
                    application=application,
                )
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
                    f"per '{name}'."
                ),
            )

        hwnd = matched_window["hwnd"]

        # --------------------------------------------------------------------
        # CLOSE
        # --------------------------------------------------------------------

        try:
            close_sent = self._send_close(
                user32=user32,
                hwnd=hwnd,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                output={
                    "requested_name": name,
                    "application": application.name,
                    "hwnd": hwnd,
                    "title": matched_window["title"],
                    "process": matched_window["process_name"],
                    "window_class": matched_window["window_class"],
                    "matched_by": matched_window["matched_by"],
                },
                error=(
                    f"Impossibile chiudere "
                    f"'{application.name}': {error}"
                ),
            )

        if not close_sent:
            return ToolResult(
                success=False,
                output={
                    "requested_name": name,
                    "application": application.name,
                    "hwnd": hwnd,
                    "title": matched_window["title"],
                    "process": matched_window["process_name"],
                    "window_class": matched_window["window_class"],
                    "matched_by": matched_window["matched_by"],
                },
                error=(
                    f"Windows non ha accettato "
                    f"la richiesta di chiusura "
                    f"di '{application.name}'."
                ),
            )

        # --------------------------------------------------------------------
        # VERIFICATION
        # --------------------------------------------------------------------

        verified = self._verify_closed(
            user32=user32,
            hwnd=hwnd,
        )

        if not verified:
            return ToolResult(
                success=False,
                output={
                    "requested_name": name,
                    "application": application.name,
                    "hwnd": hwnd,
                    "title": matched_window["title"],
                    "process": matched_window["process_name"],
                    "window_class": matched_window["window_class"],
                    "matched_by": matched_window["matched_by"],
                    "close_requested": True,
                },
                error=(
                    f"Ho inviato la richiesta di chiusura "
                    f"di '{application.name}', ma la finestra "
                    "è ancora presente. Potrebbe essere aperta "
                    "una richiesta di salvataggio o la chiusura "
                    "potrebbe essere stata rifiutata."
                ),
            )

        return ToolResult(
            success=True,
            output={
                "requested_name": name,
                "application": application.name,
                "hwnd": hwnd,
                "title": matched_window["title"],
                "process": matched_window["process_name"],
                "window_class": matched_window["window_class"],
                "matched_by": matched_window["matched_by"],
                "close_requested": True,
                "verified_closed": True,
                "user_message": (
                    f"Ho chiuso {application.name} "
                    "e ho verificato che la finestra "
                    "non è più presente."
                ),
            },
        )

    # ========================================================================
    # WINDOWS API
    # ========================================================================

    @staticmethod
    def _configure_windows_api(
        user32: Any,
        kernel32: Any,
    ) -> None:
        user32.EnumWindows.argtypes = [
            ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                wintypes.HWND,
                wintypes.LPARAM,
            ),
            wintypes.LPARAM,
        ]
        user32.EnumWindows.restype = wintypes.BOOL

        user32.IsWindow.argtypes = [
            wintypes.HWND,
        ]
        user32.IsWindow.restype = wintypes.BOOL

        user32.IsWindowVisible.argtypes = [
            wintypes.HWND,
        ]
        user32.IsWindowVisible.restype = wintypes.BOOL

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

        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL

        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE

        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

        kernel32.CloseHandle.argtypes = [
            wintypes.HANDLE,
        ]
        kernel32.CloseHandle.restype = wintypes.BOOL

    # ========================================================================
    # APPLICATION MATCHING
    # ========================================================================

    @staticmethod
    def _expected_process_names(
        application,
    ) -> set[str]:
        names: set[str] = set()

        application_name = getattr(
            application,
            "name",
            "",
        )

        if isinstance(
            application_name,
            str,
        ) and application_name.strip():
            names.add(
                CloseApplicationTool._normalize_text(
                    application_name
                )
            )

        target = getattr(
            application,
            "target",
            "",
        )

        if isinstance(
            target,
            str,
        ) and target.strip():
            target_name = Path(
                target
            ).stem

            if target_name:
                names.add(
                    CloseApplicationTool._normalize_text(
                        target_name
                    )
                )

        return {
            value
            for value in names
            if value
        }

    # ========================================================================
    # WINDOW DISCOVERY
    # ========================================================================

    def _find_best_window(
        self,
        user32: Any,
        kernel32: Any,
        query: str,
        expected_process_names: set[str],
        application,
    ) -> dict[str, Any] | None:
        candidates: list[
            dict[str, Any]
        ] = []

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        def enum_windows_proc(
            hwnd: wintypes.HWND,
            _: wintypes.LPARAM,
        ) -> bool:
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

            normalized_title = (
                self._normalize_text(
                    window_title
                )
            )

            normalized_process = (
                self._normalize_text(
                    process_name
                )
            )

            normalized_class = (
                self._normalize_text(
                    window_class
                )
            )

            application_match = (
                self._score_application_match(
                    query=query,
                    title=normalized_title,
                    process=normalized_process,
                    window_class=normalized_class,
                    expected_process_names=(
                        expected_process_names
                    ),
                    application=application,
                )
            )

            if application_match is None:
                return True

            score, matched_by = (
                application_match
            )

            candidates.append(
                {
                    "hwnd": int(hwnd),
                    "title": (
                        window_title
                        or "<titolo non disponibile>"
                    ),
                    "process_name": (
                        process_name
                        or "<processo non disponibile>"
                    ),
                    "window_class": (
                        window_class
                        or "<classe non disponibile>"
                    ),
                    "matched_by": matched_by,
                    "score": score,
                }
            )

            return True

        callback = callback_type(
            enum_windows_proc
        )

        user32.EnumWindows(
            callback,
            0,
        )

        if not candidates:
            return None

        candidates.sort(
            key=lambda candidate: (
                candidate["score"],
                len(candidate["title"]),
                candidate["hwnd"],
            )
        )

        return candidates[0]

    @staticmethod
    def _score_application_match(
        query: str,
        title: str,
        process: str,
        window_class: str,
        expected_process_names: set[str],
        application,
    ) -> tuple[int, str] | None:
        if title:
            if title == query:
                return (
                    0,
                    "title_exact",
                )

            if query and query in title:
                return (
                    1,
                    "title",
                )

        if process:
            if process in expected_process_names:
                return (
                    2,
                    "process_exact",
                )

            if query == process:
                return (
                    3,
                    "process_query_exact",
                )

            if query and query in process:
                return (
                    4,
                    "process_query",
                )

            if any(
                expected
                and (
                    expected in process
                    or process in expected
                )
                for expected
                in expected_process_names
            ):
                return (
                    5,
                    "process",
                )

        if window_class:
            if window_class == query:
                return (
                    6,
                    "class_exact",
                )

            if query and query in window_class:
                return (
                    7,
                    "class",
                )

        application_name = getattr(
            application,
            "name",
            "",
        )

        if (
            isinstance(
                application_name,
                str,
            )
            and application_name.strip()
        ):
            normalized_application_name = (
                CloseApplicationTool._normalize_text(
                    application_name
                )
            )

            if (
                normalized_application_name
                and normalized_application_name
                in title
            ):
                return (
                    8,
                    "application_title",
                )

        return None

    # ========================================================================
    # CLOSE
    # ========================================================================

    @classmethod
    def _send_close(
        cls,
        user32: Any,
        hwnd: int,
    ) -> bool:
        if not user32.IsWindow(
            hwnd
        ):
            return False

        return bool(
            user32.PostMessageW(
                hwnd,
                cls.WM_CLOSE,
                0,
                0,
            )
        )

    @classmethod
    def _verify_closed(
        cls,
        user32: Any,
        hwnd: int,
    ) -> bool:
        deadline = (
            time.monotonic()
            + cls.CLOSE_VERIFY_TIMEOUT_SECONDS
        )

        while time.monotonic() < deadline:
            if not user32.IsWindow(
                hwnd
            ):
                return True

            if not user32.IsWindowVisible(
                hwnd
            ):
                return True

            time.sleep(
                cls.CLOSE_VERIFY_INTERVAL_SECONDS
            )

        return False

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

            return Path(
                buffer.value
            ).name

        finally:
            kernel32.CloseHandle(
                process_handle
            )

    # ========================================================================
    # NORMALIZATION
    # ========================================================================

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        normalized = (
            value
            .strip()
            .lower()
        )

        normalized = " ".join(
            normalized.split()
        )

        return normalized


__all__ = [
    "CloseApplicationTool",
]
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


# ============================================================================
# FOCUS WINDOW
# ============================================================================

class FocusWindowTool(Tool):
    """
    Porta una finestra visibile in primo piano.

    La ricerca è generica e non utilizza una allowlist di applicazioni.

    IRIS può identificare la finestra tramite:
    - titolo;
    - nome del processo;
    - classe della finestra.

    Dopo il tentativo di focus, Windows viene interrogato nuovamente
    per verificare che la finestra richiesta sia realmente diventata
    la finestra in primo piano.

    Per superare le normali restrizioni Windows sul cambio della
    foreground window, il tool utilizza temporaneamente AttachThreadInput
    quando necessario.
    """

    SEARCH_TIMEOUT_SECONDS = 3.0
    SEARCH_INTERVAL_SECONDS = 0.10

    FOCUS_VERIFY_TIMEOUT_SECONDS = 1.5
    FOCUS_VERIFY_INTERVAL_SECONDS = 0.05

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="focus_window",
            description=(
                "Cerca una finestra visibile del desktop tramite "
                "titolo, nome del processo o classe della finestra, "
                "la porta in primo piano e verifica che sia realmente "
                "diventata la finestra foreground."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "Titolo, parte del titolo, nome del processo "
                            "o classe della finestra da portare in primo piano."
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

    # ========================================================================
    # EXECUTE
    # ========================================================================

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

        self._configure_windows_api(
            user32,
            kernel32,
        )

        normalized_query = self._normalize_text(
            title
        )

        if not normalized_query:
            return ToolResult(
                success=False,
                error=(
                    "Il titolo non contiene un valore ricercabile."
                ),
            )

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
                    f"per '{title}' entro "
                    f"{self.SEARCH_TIMEOUT_SECONDS:.1f} secondi."
                ),
            )

        hwnd = matched_window["hwnd"]

        # --------------------------------------------------------------------
        # FOCUS
        # --------------------------------------------------------------------

        try:
            focus_success = self._focus_window(
                user32=user32,
                kernel32=kernel32,
                hwnd=hwnd,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                output={
                    "hwnd": hwnd,
                    "title": matched_window["title"],
                    "process": matched_window["process_name"],
                    "window_class": matched_window["window_class"],
                    "matched_by": matched_window["matched_by"],
                },
                error=(
                    f"Impossibile controllare la finestra: "
                    f"{error}"
                ),
            )

        if not focus_success:
            return ToolResult(
                success=False,
                output={
                    "hwnd": hwnd,
                    "title": matched_window["title"],
                    "process": matched_window["process_name"],
                    "window_class": matched_window["window_class"],
                    "matched_by": matched_window["matched_by"],
                },
                error=(
                    f"La finestra '{matched_window['title']}' è stata trovata "
                    f"(processo: {matched_window['process_name']}, "
                    f"classe: {matched_window['window_class']}), "
                    "ma Windows non ha consentito di portarla "
                    "in primo piano."
                ),
            )

        # --------------------------------------------------------------------
        # FOREGROUND VERIFICATION
        # --------------------------------------------------------------------

        verified = self._verify_foreground(
            user32=user32,
            hwnd=hwnd,
        )

        if not verified:
            return ToolResult(
                success=False,
                output={
                    "hwnd": hwnd,
                    "title": matched_window["title"],
                    "process": matched_window["process_name"],
                    "window_class": matched_window["window_class"],
                    "matched_by": matched_window["matched_by"],
                },
                error=(
                    f"La finestra '{matched_window['title']}' "
                    "è stata trovata ma non risulta "
                    "in primo piano dopo la verifica."
                ),
            )

        return ToolResult(
            success=True,
            output={
                "title": matched_window["title"],
                "hwnd": hwnd,
                "process": matched_window["process_name"],
                "window_class": matched_window["window_class"],
                "matched_by": matched_window["matched_by"],
                "verified_foreground": True,
                "user_message": (
                    f"Ho portato '{matched_window['title']}' "
                    "in primo piano e ho verificato il focus."
                ),
            },
        )

    # ========================================================================
    # WINDOWS API CONFIGURATION
    # ========================================================================

    @staticmethod
    def _configure_windows_api(
        user32: Any,
        kernel32: Any,
    ) -> None:
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND

        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        user32.SetForegroundWindow.argtypes = [
            wintypes.HWND,
        ]
        user32.SetForegroundWindow.restype = wintypes.BOOL

        user32.BringWindowToTop.argtypes = [
            wintypes.HWND,
        ]
        user32.BringWindowToTop.restype = wintypes.BOOL

        user32.ShowWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
        ]
        user32.ShowWindow.restype = wintypes.BOOL

        user32.IsWindow.argtypes = [
            wintypes.HWND,
        ]
        user32.IsWindow.restype = wintypes.BOOL

        user32.IsWindowVisible.argtypes = [
            wintypes.HWND,
        ]
        user32.IsWindowVisible.restype = wintypes.BOOL

        user32.IsIconic.argtypes = [
            wintypes.HWND,
        ]
        user32.IsIconic.restype = wintypes.BOOL

        user32.AttachThreadInput.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.BOOL,
        ]
        user32.AttachThreadInput.restype = wintypes.BOOL

        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    # ========================================================================
    # FOCUS IMPLEMENTATION
    # ========================================================================

    @staticmethod
    def _focus_window(
        user32: Any,
        kernel32: Any,
        hwnd: int,
    ) -> bool:
        """
        Tenta di portare una finestra in foreground.

        Strategia:

        1. verifica che HWND sia ancora valido;
        2. ripristina la finestra se minimizzata;
        3. prova il percorso normale;
        4. se Windows lo rifiuta, collega temporaneamente il thread
           di IRIS al thread della finestra attualmente foreground;
        5. riprova BringWindowToTop + SetForegroundWindow;
        6. scollega sempre i thread nel finally.
        """

        if not user32.IsWindow(
            hwnd
        ):
            return False

        SW_RESTORE = 9

        if user32.IsIconic(
            hwnd
        ):
            user32.ShowWindow(
                hwnd,
                SW_RESTORE,
            )

        foreground_before = (
            user32.GetForegroundWindow()
        )

        if int(
            foreground_before or 0
        ) == int(hwnd):
            return True

        # --------------------------------------------------------------------
        # FIRST ATTEMPT
        # --------------------------------------------------------------------

        user32.BringWindowToTop(
            hwnd
        )

        if user32.SetForegroundWindow(
            hwnd
        ):
            return True

        # --------------------------------------------------------------------
        # FOREGROUND THREAD
        # --------------------------------------------------------------------

        current_thread_id = (
            kernel32.GetCurrentThreadId()
        )

        foreground_thread_id = (
            user32.GetWindowThreadProcessId(
                foreground_before,
                None,
            )
            if foreground_before
            else 0
        )

        if (
            not foreground_thread_id
            or current_thread_id
            == foreground_thread_id
        ):
            return False

        attached = False

        try:
            attached = bool(
                user32.AttachThreadInput(
                    current_thread_id,
                    foreground_thread_id,
                    True,
                )
            )

            if not attached:
                return False

            user32.BringWindowToTop(
                hwnd
            )

            # Dopo aver condiviso temporaneamente l'input queue,
            # Windows permette al processo di IRIS di riprovare
            # il cambio foreground.
            user32.SetForegroundWindow(
                hwnd
            )

            return True

        finally:
            if attached:
                user32.AttachThreadInput(
                    current_thread_id,
                    foreground_thread_id,
                    False,
                )

    # ========================================================================
    # FOREGROUND VERIFICATION
    # ========================================================================

    @staticmethod
    def _verify_foreground(
        user32: Any,
        hwnd: int,
    ) -> bool:
        deadline = (
            time.monotonic()
            + FocusWindowTool.FOCUS_VERIFY_TIMEOUT_SECONDS
        )

        while time.monotonic() < deadline:
            foreground = (
                user32.GetForegroundWindow()
            )

            if int(
                foreground or 0
            ) == int(hwnd):
                return True

            time.sleep(
                FocusWindowTool.FOCUS_VERIFY_INTERVAL_SECONDS
            )

        return False

    # ========================================================================
    # WINDOW DISCOVERY
    # ========================================================================

    def _find_best_window(
        self,
        user32: Any,
        kernel32: Any,
        query: str,
    ) -> dict[str, Any] | None:
        candidates: list[
            dict[str, Any]
        ] = []

        enum_windows_proc_type = ctypes.WINFUNCTYPE(
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

            match = self._score_window_match(
                query=query,
                title=normalized_window_title,
                process=normalized_process_name,
                window_class=normalized_window_class,
            )

            if match is None:
                return True

            score, matched_by = match

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

        callback = (
            enum_windows_proc_type(
                enum_windows_proc
            )
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

    # ========================================================================
    # WINDOW MATCHING
    # ========================================================================

    @staticmethod
    def _score_window_match(
        query: str,
        title: str,
        process: str,
        window_class: str,
    ) -> tuple[int, str] | None:
        if not query:
            return None

        # --------------------------------------------------------------------
        # TITLE
        # --------------------------------------------------------------------

        if title == query:
            return (
                0,
                "title_exact",
            )

        if query in title:
            return (
                1,
                "title",
            )

        # --------------------------------------------------------------------
        # PROCESS
        # --------------------------------------------------------------------

        if process == query:
            return (
                2,
                "process_exact",
            )

        if query in process:
            return (
                3,
                "process",
            )

        # --------------------------------------------------------------------
        # WINDOW CLASS
        # --------------------------------------------------------------------

        if window_class == query:
            return (
                4,
                "class_exact",
            )

        if query in window_class:
            return (
                5,
                "class",
            )

        return None

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

        normalized = " ".join(
            normalized.split()
        )

        return normalized.strip()


__all__ = [
    "FocusWindowTool",
]
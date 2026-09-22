from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.tools.application_resolver import (
    ApplicationResolver,
)
from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


# ============================================================================
# WINDOWS PROCESS HELPERS
# ============================================================================

def _windows_detached_flags() -> int:
    """
    Crea un processo Windows completamente separato dalla console di IRIS.

    Questo è importante per applicazioni come Discord/Vencord che possono
    essere applicazioni Electron/console e scrivere direttamente sulla
    console ereditata dal processo padre.
    """

    if os.name != "nt":
        return 0

    detached_process = getattr(
        subprocess,
        "DETACHED_PROCESS",
        0x00000008,
    )

    create_new_process_group = getattr(
        subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        0x00000200,
    )

    return (
        detached_process
        | create_new_process_group
    )


def _windows_no_console_flags() -> int:
    """
    Flag utilizzati per i processi di servizio di IRIS che devono invece
    essere eseguiti senza aprire una console.

    Viene usato per PowerShell, where.exe e altri processi interni,
    NON per le applicazioni GUI dell'utente.
    """

    if os.name != "nt":
        return 0

    return getattr(
        subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
    )


def _windows_powershell_executable() -> str:
    """
    Restituisce il percorso dell'eseguibile Windows PowerShell.

    Non dipende dal PATH del processo che esegue IRIS.
    """

    if os.name != "nt":
        raise OSError(
            "PowerShell Windows è disponibile solo su Windows."
        )

    system_root = os.environ.get(
        "SystemRoot"
    )

    if not system_root:
        raise OSError(
            "La variabile d'ambiente SystemRoot non è disponibile."
        )

    executable = (
        Path(system_root)
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )

    if not executable.exists():
        raise OSError(
            f"PowerShell non trovata in '{executable}'."
        )

    return str(
        executable
    )


# ============================================================================
# APPLICATION CONTROL
# ============================================================================

class OpenApplicationTool(Tool):
    """
    Cerca, apre e verifica un'applicazione Windows.

    Caratteristiche:

    - nessuna allowlist di applicazioni;
    - riconoscimento tramite ApplicationResolver;
    - riconoscimento delle applicazioni già in esecuzione;
    - supporto a Start Menu;
    - supporto a Windows Start Apps / AppID;
    - supporto a eseguibili;
    - fallback per eseguibili presenti nel PATH;
    - applicazioni GUI completamente separate dalla console di IRIS;
    - verifica reale tramite processi Windows.
    """

    def __init__(
        self,
        resolver: ApplicationResolver | None = None,
        verification_timeout: float = 5.0,
        verification_interval: float = 0.25,
    ) -> None:
        if verification_timeout <= 0:
            raise ValueError(
                "verification_timeout deve essere maggiore di zero."
            )

        if verification_interval <= 0:
            raise ValueError(
                "verification_interval deve essere maggiore di zero."
            )

        self.resolver = (
            resolver
            or ApplicationResolver()
        )

        self.verification_timeout = (
            verification_timeout
        )

        self.verification_interval = (
            verification_interval
        )

        self._definition = ToolDefinition(
            name="open_application",
            description=(
                "Cerca, apre e verifica l'avvio di "
                "un'applicazione presente sul PC "
                "riconoscendola dal nome richiesto. "
                "Riconosce anche applicazioni già aperte."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Nome dell'applicazione da aprire."
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

        # --------------------------------------------------------------------
        # DISCOVERY
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
        # PROCESS DISCOVERY BEFORE LAUNCH
        # --------------------------------------------------------------------

        try:
            processes_before = (
                self._discover_processes()
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    "Non riesco a controllare "
                    f"i processi del PC: {error}"
                ),
            )

        # --------------------------------------------------------------------
        # ALREADY RUNNING
        # --------------------------------------------------------------------

        already_running = self._find_matching_process(
            application=application,
            processes=processes_before,
        )

        if already_running is not None:
            return ToolResult(
                success=True,
                output={
                    "requested_name": name,
                    "application": application.name,
                    "source": application.source,
                    "target": application.target,
                    "launch_pid": None,
                    "verified_pid": already_running["pid"],
                    "verified_process_name": (
                        already_running["name"]
                    ),
                    "already_running": True,
                    "user_message": (
                        f"{application.name} "
                        "è già in esecuzione."
                    ),
                },
            )

        # --------------------------------------------------------------------
        # LAUNCH
        # --------------------------------------------------------------------

        try:
            launch_pid = self._launch(
                application
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile aprire "
                    f"'{application.name}': {error}"
                ),
            )

        # --------------------------------------------------------------------
        # VERIFY
        # --------------------------------------------------------------------

        try:
            verified_process = (
                self._verify_launch(
                    application=application,
                    processes_before=processes_before,
                )
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ) as error:
            return ToolResult(
                success=False,
                output={
                    "requested_name": name,
                    "application": application.name,
                    "source": application.source,
                    "target": application.target,
                    "launch_pid": launch_pid,
                },
                error=(
                    "L'applicazione è stata avviata, "
                    "ma non è stato possibile completare "
                    f"la verifica: {error}"
                ),
            )

        if verified_process is None:
            return ToolResult(
                success=False,
                output={
                    "requested_name": name,
                    "application": application.name,
                    "source": application.source,
                    "target": application.target,
                    "launch_pid": launch_pid,
                },
                error=(
                    f"Ho avviato '{application.name}', "
                    "ma non sono riuscito a verificare "
                    "che sia effettivamente in esecuzione."
                ),
            )

        return ToolResult(
            success=True,
            output={
                "requested_name": name,
                "application": application.name,
                "source": application.source,
                "target": application.target,
                "launch_pid": launch_pid,
                "verified_pid": verified_process["pid"],
                "verified_process_name": (
                    verified_process["name"]
                ),
                "already_running": False,
                "user_message": (
                    f"Ho aperto {application.name} "
                    "e ho verificato che è in esecuzione."
                ),
            },
        )

    # ========================================================================
    # LAUNCH
    # ========================================================================

    def _launch(
        self,
        application,
    ) -> int | None:
        source = getattr(
            application,
            "source",
            None,
        )

        target = getattr(
            application,
            "target",
            None,
        )

        # --------------------------------------------------------------------
        # START MENU SHORTCUT
        # --------------------------------------------------------------------

        if source == "start_menu":
            if os.name != "nt":
                raise OSError(
                    "Le scorciatoie Start Menu sono supportate "
                    "solo su Windows."
                )

            if not isinstance(
                target,
                str,
            ) or not target:
                raise OSError(
                    "La scorciatoia Start Menu non ha un target valido."
                )

            shortcut = Path(
                target
            )

            if not shortcut.exists():
                raise OSError(
                    f"La scorciatoia '{shortcut}' non esiste più."
                )

            return self._launch_detached(
                str(shortcut)
            )

        # --------------------------------------------------------------------
        # WINDOWS REGISTERED APP
        # --------------------------------------------------------------------

        if source == "windows_start_apps":
            if os.name != "nt":
                raise OSError(
                    "Le applicazioni Windows registrate "
                    "sono supportate solo su Windows."
                )

            app_id = getattr(
                application,
                "app_id",
                None,
            )

            if not isinstance(
                app_id,
                str,
            ) or not app_id.strip():
                raise OSError(
                    "L'applicazione Windows non ha un AppID valido."
                )

            command = [
                "explorer.exe",
                (
                    "shell:AppsFolder\\"
                    f"{app_id}"
                ),
            ]

            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=_windows_detached_flags(),
            )

            return process.pid

        # --------------------------------------------------------------------
        # GENERIC EXECUTABLE / PATH
        # --------------------------------------------------------------------

        if not isinstance(
            target,
            str,
        ) or not target.strip():
            raise OSError(
                "L'applicazione non ha un target valido."
            )

        target = target.strip()

        resolved_target = self._resolve_executable_target(
            target
        )

        return self._launch_detached(
            resolved_target
        )

    @staticmethod
    def _launch_detached(
        target: str,
    ) -> int | None:
        """
        Avvia un programma Windows senza condividere la console di IRIS.

        IMPORTANTE:
        DETACHED_PROCESS è diverso da CREATE_NO_WINDOW.

        CREATE_NO_WINDOW evita una nuova console per determinati processi,
        ma non è sufficiente per un'applicazione che nasce come processo
        console e può ereditare la console padre.

        DETACHED_PROCESS crea invece il processo senza una console associata.
        """

        if os.name != "nt":
            process = subprocess.Popen(
                [target],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )

            return process.pid

        path = Path(
            target
        )

        # --------------------------------------------------------------------
        # .LNK
        # --------------------------------------------------------------------

        if path.suffix.lower() == ".lnk":
            if not path.exists():
                raise OSError(
                    f"La scorciatoia '{path}' non esiste più."
                )

            # Usiamo explorer in un processo completamente detached.
            process = subprocess.Popen(
                [
                    "explorer.exe",
                    str(path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=_windows_detached_flags(),
            )

            return process.pid

        # --------------------------------------------------------------------
        # EXE
        # --------------------------------------------------------------------

        if path.exists():
            executable = str(
                path
            )

        else:
            executable = target

        process = subprocess.Popen(
            [executable],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=_windows_detached_flags(),
        )

        return process.pid

    @staticmethod
    def _resolve_executable_target(
        target: str,
    ) -> str:
        """
        Risolve un eseguibile eventualmente presente nel PATH.
        """

        path = Path(
            target
        )

        if path.exists():
            return str(
                path
            )

        if os.name == "nt":
            try:
                completed = subprocess.run(
                    [
                        "where.exe",
                        target,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    creationflags=_windows_no_console_flags(),
                )

                if completed.returncode == 0:
                    candidates = [
                        line.strip()
                        for line
                        in completed.stdout.splitlines()
                        if line.strip()
                    ]

                    for candidate in candidates:
                        candidate_path = Path(
                            candidate
                        )

                        if candidate_path.exists():
                            return str(
                                candidate_path
                            )

            except (
                OSError,
                subprocess.SubprocessError,
            ):
                pass

        return target

    # ========================================================================
    # PROCESS DISCOVERY
    # ========================================================================

    @staticmethod
    def _discover_processes() -> list[dict[str, Any]]:
        if os.name != "nt":
            return []

        command = [
            _windows_powershell_executable(),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "Get-Process | "
                "Select-Object Id,ProcessName,Path | "
                "ConvertTo-Json -Compress"
            ),
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10.0,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            creationflags=_windows_no_console_flags(),
        )

        if completed.returncode != 0:
            raise OSError(
                completed.stderr.strip()
                or "Impossibile leggere i processi."
            )

        raw = completed.stdout.strip()

        if not raw:
            return []

        try:
            data = json.loads(
                raw
            )

        except json.JSONDecodeError as error:
            raise OSError(
                f"Risposta processi non valida: {error}"
            ) from error

        if isinstance(
            data,
            dict,
        ):
            data = [
                data
            ]

        if not isinstance(
            data,
            list,
        ):
            return []

        processes: list[
            dict[str, Any]
        ] = []

        for item in data:
            if not isinstance(
                item,
                dict,
            ):
                continue

            pid = item.get(
                "Id"
            )

            name = item.get(
                "ProcessName"
            )

            path = item.get(
                "Path"
            )

            if not isinstance(
                pid,
                int,
            ):
                continue

            if not isinstance(
                name,
                str,
            ):
                continue

            processes.append(
                {
                    "pid": pid,
                    "name": name,
                    "path": (
                        path
                        if isinstance(
                            path,
                            str,
                        )
                        else None
                    ),
                }
            )

        return processes

    # ========================================================================
    # VERIFICATION
    # ========================================================================

    def _verify_launch(
        self,
        application,
        processes_before: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        before_pids = {
            process["pid"]
            for process
            in processes_before
        }

        expected_names = (
            self._expected_process_names(
                application
            )
        )

        deadline = (
            time.monotonic()
            + self.verification_timeout
        )

        while time.monotonic() < deadline:
            processes_after = (
                self._discover_processes()
            )

            new_candidates = [
                process
                for process
                in processes_after
                if process["pid"] not in before_pids
                and self._process_matches(
                    process=process,
                    expected_names=expected_names,
                    application=application,
                )
            ]

            if new_candidates:
                new_candidates.sort(
                    key=lambda process: process["pid"]
                )

                return new_candidates[0]

            existing_candidates = [
                process
                for process
                in processes_after
                if self._process_matches(
                    process=process,
                    expected_names=expected_names,
                    application=application,
                )
            ]

            if existing_candidates:
                existing_candidates.sort(
                    key=lambda process: process["pid"]
                )

                return existing_candidates[0]

            time.sleep(
                self.verification_interval
            )

        return None

    @staticmethod
    def _find_matching_process(
        application,
        processes: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        expected_names = (
            OpenApplicationTool._expected_process_names(
                application
            )
        )

        candidates = [
            process
            for process
            in processes
            if OpenApplicationTool._process_matches(
                process=process,
                expected_names=expected_names,
                application=application,
            )
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda process: process["pid"]
        )

        return candidates[0]

    # ========================================================================
    # PROCESS MATCHING
    # ========================================================================

    @staticmethod
    def _expected_process_names(
        application,
    ) -> set[str]:
        names: set[str] = set()

        target = getattr(
            application,
            "target",
            "",
        )

        if isinstance(
            target,
            str,
        ) and target:
            target_path = Path(
                target
            )

            target_name = (
                target_path.stem.strip()
            )

            if target_name:
                names.add(
                    OpenApplicationTool._normalize_name(
                        target_name
                    )
                )

        application_name = getattr(
            application,
            "name",
            "",
        )

        if isinstance(
            application_name,
            str,
        ) and application_name:
            names.add(
                OpenApplicationTool._normalize_name(
                    application_name
                )
            )

        app_id = getattr(
            application,
            "app_id",
            None,
        )

        if isinstance(
            app_id,
            str,
        ) and app_id:
            app_id_name = app_id.split(
                "!",
                1,
            )[-1]

            if app_id_name:
                names.add(
                    OpenApplicationTool._normalize_name(
                        app_id_name
                    )
                )

        return {
            name
            for name in names
            if name
        }

    @staticmethod
    def _process_matches(
        process: dict[str, Any],
        expected_names: set[str],
        application,
    ) -> bool:
        process_name = process.get(
            "name"
        )

        process_path = process.get(
            "path"
        )

        if isinstance(
            process_name,
            str,
        ):
            normalized_process_name = (
                OpenApplicationTool._normalize_name(
                    process_name
                )
            )

            if normalized_process_name in expected_names:
                return True

        if isinstance(
            process_path,
            str,
        ) and process_path:
            executable_name = Path(
                process_path
            ).stem

            normalized_executable = (
                OpenApplicationTool._normalize_name(
                    executable_name
                )
            )

            if normalized_executable in expected_names:
                return True

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
            and isinstance(
                process_name,
                str,
            )
        ):
            normalized_application = (
                OpenApplicationTool._normalize_name(
                    application_name
                )
            )

            normalized_process = (
                OpenApplicationTool._normalize_name(
                    process_name
                )
            )

            if (
                normalized_application
                and (
                    normalized_application
                    in normalized_process
                    or normalized_process
                    in normalized_application
                )
            ):
                return True

        return False

    # ========================================================================
    # NAME NORMALIZATION
    # ========================================================================

    @staticmethod
    def _normalize_name(
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .lower()
            .removesuffix(".exe")
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
        )


# ============================================================================
# READ FILE
# ============================================================================

class ReadFileTool(Tool):
    """
    Legge un file di testo presente in uno dei percorsi consentiti.
    """

    def __init__(
        self,
        allowed_roots: list[str | Path] | None = None,
        max_bytes: int = 1_000_000,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError(
                "max_bytes deve essere maggiore di zero."
            )

        self.allowed_roots = [
            Path(root).resolve()
            for root in (
                allowed_roots
                or [Path.cwd()]
            )
        ]

        self.max_bytes = max_bytes

        self._definition = ToolDefinition(
            name="read_file",
            description=(
                "Legge il contenuto di un file di testo "
                "presente in un percorso consentito."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Percorso del file da leggere."
                        ),
                    },
                },
                "required": [
                    "path",
                ],
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
    def definition(
        self,
    ) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        path = arguments.get(
            "path"
        )

        if not isinstance(
            path,
            str,
        ):
            return ToolResult(
                success=False,
                error="Il percorso deve essere una stringa.",
            )

        path = path.strip()

        if not path:
            return ToolResult(
                success=False,
                error="Il percorso non può essere vuoto.",
            )

        try:
            resolved_path = Path(
                path
            ).resolve()

            if not self._is_allowed(
                resolved_path
            ):
                return ToolResult(
                    success=False,
                    error=(
                        "Il file richiesto si trova "
                        "fuori dai percorsi consentiti."
                    ),
                )

            if not resolved_path.exists():
                return ToolResult(
                    success=False,
                    error=(
                        f"Il file '{resolved_path}' "
                        "non esiste."
                    ),
                )

            if not resolved_path.is_file():
                return ToolResult(
                    success=False,
                    error=(
                        f"'{resolved_path}' "
                        "non è un file."
                    ),
                )

            size = resolved_path.stat().st_size

            if size > self.max_bytes:
                return ToolResult(
                    success=False,
                    error=(
                        f"Il file è troppo grande "
                        f"({size} byte, massimo "
                        f"{self.max_bytes})."
                    ),
                )

            content = resolved_path.read_text(
                encoding="utf-8"
            )

            return ToolResult(
                success=True,
                output={
                    "path": str(resolved_path),
                    "content": content,
                    "bytes": size,
                    "user_message": (
                        f"Ho letto il file "
                        f"'{resolved_path.name}'."
                    ),
                },
            )

        except (
            OSError,
            UnicodeError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile leggere il file: {error}"
                ),
            )

    def _is_allowed(
        self,
        path: Path,
    ) -> bool:
        return any(
            self._is_relative_to(
                path,
                root,
            )
            for root in self.allowed_roots
        )

    @staticmethod
    def _is_relative_to(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.relative_to(
                root
            )
            return True
        except ValueError:
            return False


# ============================================================================
# WRITE FILE
# ============================================================================

class WriteFileTool(Tool):
    """
    Scrive un file di testo in uno dei percorsi consentiti.
    """

    def __init__(
        self,
        allowed_roots: list[str | Path] | None = None,
        max_bytes: int = 1_000_000,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError(
                "max_bytes deve essere maggiore di zero."
            )

        self.allowed_roots = [
            Path(root).resolve()
            for root in (
                allowed_roots
                or [Path.cwd()]
            )
        ]

        self.max_bytes = max_bytes

        self._definition = ToolDefinition(
            name="write_file",
            description=(
                "Scrive contenuto testuale in un file "
                "presente in un percorso consentito."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Percorso del file da scrivere."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Contenuto testuale da scrivere."
                        ),
                    },
                },
                "required": [
                    "path",
                    "content",
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
    def definition(
        self,
    ) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        path = arguments.get(
            "path"
        )

        content = arguments.get(
            "content"
        )

        if not isinstance(
            path,
            str,
        ):
            return ToolResult(
                success=False,
                error="Il percorso deve essere una stringa.",
            )

        if not isinstance(
            content,
            str,
        ):
            return ToolResult(
                success=False,
                error="Il contenuto deve essere una stringa.",
            )

        path = path.strip()

        if not path:
            return ToolResult(
                success=False,
                error="Il percorso non può essere vuoto.",
            )

        try:
            resolved_path = Path(
                path
            ).resolve()

            if not self._is_allowed(
                resolved_path
            ):
                return ToolResult(
                    success=False,
                    error=(
                        "Il file richiesto si trova "
                        "fuori dai percorsi consentiti."
                    ),
                )

            content_bytes = content.encode(
                "utf-8"
            )

            if len(content_bytes) > self.max_bytes:
                return ToolResult(
                    success=False,
                    error=(
                        f"Il contenuto è troppo grande "
                        f"({len(content_bytes)} byte, massimo "
                        f"{self.max_bytes})."
                    ),
                )

            resolved_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            resolved_path.write_text(
                content,
                encoding="utf-8",
            )

            return ToolResult(
                success=True,
                output={
                    "path": str(resolved_path),
                    "bytes": len(content_bytes),
                    "user_message": (
                        f"Ho scritto il file "
                        f"'{resolved_path.name}'."
                    ),
                },
            )

        except (
            OSError,
            UnicodeError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile scrivere il file: {error}"
                ),
            )

    def _is_allowed(
        self,
        path: Path,
    ) -> bool:
        return any(
            self._is_relative_to(
                path,
                root,
            )
            for root in self.allowed_roots
        )

    @staticmethod
    def _is_relative_to(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.relative_to(
                root
            )
            return True
        except ValueError:
            return False


# ============================================================================
# RUN COMMAND
# ============================================================================

class RunCommandTool(Tool):
    """
    Esegue comandi di sistema esplicitamente consentiti.

    stdout e stderr vengono sempre catturati e non vengono mai
    lasciati collegati alla console interattiva di IRIS.
    """

    def __init__(self) -> None:
        self._commands = {
            "python_version": [
                "python",
                "--version",
            ],
            "whoami": [
                "whoami",
            ],
        }

        self._definition = ToolDefinition(
            name="run_command",
            description=(
                "Esegue uno dei comandi di sistema "
                "esplicitamente consentiti da IRIS."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "Nome del comando consentito."
                        ),
                    },
                },
                "required": [
                    "command",
                ],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset(
                {
                    Permission.EXECUTE.value,
                }
            ),
        )

    @property
    def definition(
        self,
    ) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        command_name = arguments.get(
            "command"
        )

        if not isinstance(
            command_name,
            str,
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il nome del comando "
                    "deve essere una stringa."
                ),
            )

        command_name = command_name.strip()

        if not command_name:
            return ToolResult(
                success=False,
                error=(
                    "Il nome del comando "
                    "non può essere vuoto."
                ),
            )

        command = self._commands.get(
            command_name
        )

        if command is None:
            return ToolResult(
                success=False,
                error=(
                    f"Il comando '{command_name}' "
                    "non è consentito."
                ),
            )

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                shell=False,
                stdin=subprocess.DEVNULL,
                creationflags=_windows_no_console_flags(),
            )

            output = completed.stdout.strip()
            error = completed.stderr.strip()

            if completed.returncode != 0:
                return ToolResult(
                    success=False,
                    output={
                        "command": command_name,
                        "stdout": output,
                        "stderr": error,
                        "returncode": completed.returncode,
                    },
                    error=(
                        error
                        or (
                            f"Il comando '{command_name}' "
                            "ha restituito un errore."
                        )
                    ),
                )

            return ToolResult(
                success=True,
                output={
                    "command": command_name,
                    "stdout": output,
                    "stderr": error,
                    "returncode": completed.returncode,
                    "user_message": (
                        f"Ho eseguito il comando "
                        f"'{command_name}'."
                    ),
                },
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile eseguire "
                    f"'{command_name}': {error}"
                ),
            )
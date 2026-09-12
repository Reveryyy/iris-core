from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from app.tools.application_resolver import (
    ApplicationResolver,
)
from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class OpenApplicationTool(Tool):
    """
    Apre automaticamente un'applicazione presente sul PC.

    L'applicazione non viene scelta tramite allowlist.
    Il nome richiesto viene risolto da ApplicationResolver.
    """

    def __init__(
        self,
        resolver: ApplicationResolver | None = None,
    ) -> None:

        self.resolver = (
            resolver
            or ApplicationResolver()
        )

        self._definition = ToolDefinition(
            name="open_application",
            description=(
                "Cerca e apre un'applicazione presente "
                "sul PC riconoscendola dal nome richiesto."
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

        try:
            process = self._launch(
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

        return ToolResult(
            success=True,
            output={
                "requested_name": name,
                "application": application.name,
                "source": application.source,
                "target": application.target,
                "pid": process,
            },
        )

    # ========================================================================
    # LAUNCH
    # ========================================================================

    @staticmethod
    def _launch(
        application,
    ) -> int | None:

        # --------------------------------------------------------------------
        # START MENU .LNK
        # --------------------------------------------------------------------

        if application.source == "start_menu":

            if os.name != "nt":
                raise OSError(
                    "Le scorciatoie Start Menu sono supportate "
                    "solo su Windows."
                )

            os.startfile(
                application.target
            )

            return None

        # --------------------------------------------------------------------
        # WINDOWS REGISTERED APP
        # --------------------------------------------------------------------

        if (
            application.source
            == "windows_start_apps"
        ):

            if os.name != "nt":
                raise OSError(
                    "Le applicazioni Windows registrate "
                    "sono supportate solo su Windows."
                )

            command = [
                "explorer.exe",
                (
                    "shell:AppsFolder\\"
                    f"{application.app_id}"
                ),
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=False,
            )

            return process.pid

        # --------------------------------------------------------------------
        # EXE / REGISTRY / PATH
        # --------------------------------------------------------------------

        process = subprocess.Popen(
            [application.target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            shell=False,
        )

        return process.pid


class ReadFileTool(Tool):
    """
    Legge un file esclusivamente dentro directory autorizzate.
    """

    def __init__(
        self,
        allowed_roots: list[str | Path] | None = None,
        max_bytes: int = 1_000_000,
    ) -> None:

        self.allowed_roots = tuple(
            Path(root).resolve()
            for root in (
                allowed_roots
                or [
                    Path.cwd(),
                ]
            )
        )

        self.max_bytes = max_bytes

        self._definition = ToolDefinition(
            name="read_file",
            description=(
                "Legge il contenuto di un file situato "
                "in una directory autorizzata."
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

        raw_path = arguments.get(
            "path"
        )

        if not isinstance(
            raw_path,
            str,
        ):
            return ToolResult(
                success=False,
                error="Il percorso deve essere una stringa.",
            )

        if not raw_path.strip():
            return ToolResult(
                success=False,
                error="Il percorso non può essere vuoto.",
            )

        try:
            path = (
                Path(raw_path)
                .expanduser()
                .resolve()
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=f"Percorso non valido: {error}",
            )

        if not self._is_allowed(
            path
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il file si trova fuori dalle "
                    "directory autorizzate."
                ),
            )

        if not path.exists():
            return ToolResult(
                success=False,
                error="Il file non esiste.",
            )

        if not path.is_file():
            return ToolResult(
                success=False,
                error="Il percorso indicato non è un file.",
            )

        try:
            size = path.stat().st_size

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    "Impossibile leggere le informazioni "
                    f"del file: {error}"
                ),
            )

        if size > self.max_bytes:
            return ToolResult(
                success=False,
                error=(
                    f"Il file supera il limite di "
                    f"{self.max_bytes} byte."
                ),
            )

        try:
            content = path.read_text(
                encoding="utf-8"
            )

        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                error=(
                    "Il file non è un file di testo UTF-8."
                ),
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile leggere il file: {error}"
                ),
            )

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "content": content,
                "bytes": size,
            },
        )

    def _is_allowed(
        self,
        path: Path,
    ) -> bool:

        return any(
            self._is_within(
                path,
                root,
            )
            for root in self.allowed_roots
        )

    @staticmethod
    def _is_within(
        path: Path,
        root: Path,
    ) -> bool:

        try:
            path.relative_to(
                root
            )

        except ValueError:
            return False

        return True


class WriteFileTool(Tool):
    """
    Scrive file esclusivamente dentro directory autorizzate.
    """

    def __init__(
        self,
        allowed_roots: list[str | Path] | None = None,
        max_bytes: int = 1_000_000,
    ) -> None:

        self.allowed_roots = tuple(
            Path(root).resolve()
            for root in (
                allowed_roots
                or [
                    Path.cwd(),
                ]
            )
        )

        self.max_bytes = max_bytes

        self._definition = ToolDefinition(
            name="write_file",
            description=(
                "Scrive contenuto in un file situato "
                "in una directory autorizzata."
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
                            "Contenuto da scrivere."
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

        raw_path = arguments.get(
            "path"
        )

        content = arguments.get(
            "content"
        )

        if not isinstance(
            raw_path,
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

        if not raw_path.strip():
            return ToolResult(
                success=False,
                error="Il percorso non può essere vuoto.",
            )

        try:
            path = (
                Path(raw_path)
                .expanduser()
                .resolve()
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=f"Percorso non valido: {error}",
            )

        if not self._is_allowed(
            path
        ):
            return ToolResult(
                success=False,
                error=(
                    "Il file si trova fuori dalle "
                    "directory autorizzate."
                ),
            )

        content_bytes = content.encode(
            "utf-8"
        )

        if len(content_bytes) > self.max_bytes:
            return ToolResult(
                success=False,
                error=(
                    f"Il contenuto supera il limite "
                    f"di {self.max_bytes} byte."
                ),
            )

        try:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            path.write_text(
                content,
                encoding="utf-8",
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile scrivere il file: {error}"
                ),
            )

        return ToolResult(
            success=True,
            output={
                "path": str(path),
                "bytes": len(content_bytes),
            },
        )

    def _is_allowed(
        self,
        path: Path,
    ) -> bool:

        return any(
            self._is_within(
                path,
                root,
            )
            for root in self.allowed_roots
        )

    @staticmethod
    def _is_within(
        path: Path,
        root: Path,
    ) -> bool:

        try:
            path.relative_to(
                root
            )

        except ValueError:
            return False

        return True


class RunCommandTool(Tool):
    """
    Esegue esclusivamente comandi presenti in una allowlist.

    Non usa shell=True e non permette comandi arbitrari.
    """

    def __init__(
        self,
        allowed_commands: dict[str, list[str]] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:

        self.allowed_commands = (
            allowed_commands
            or {
                "python_version": [
                    "python",
                    "--version",
                ],
                "whoami": [
                    "whoami",
                ],
            }
        )

        self.timeout_seconds = timeout_seconds

        self._definition = ToolDefinition(
            name="run_command",
            description=(
                "Esegue un comando presente nella "
                "allowlist del sistema."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "Nome del comando autorizzato."
                        ),
                    },
                },
                "required": [
                    "command",
                ],
                "additionalProperties": False,
            },
            risk_level="high",
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
                error="Il comando deve essere una stringa.",
            )

        command_name = command_name.strip()

        if not command_name:
            return ToolResult(
                success=False,
                error="Il comando non può essere vuoto.",
            )

        command = self.allowed_commands.get(
            command_name
        )

        if command is None:
            return ToolResult(
                success=False,
                error=(
                    f"Il comando '{command_name}' "
                    "non è presente nella allowlist."
                ),
            )

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=(
                    f"Il comando ha superato il timeout "
                    f"di {self.timeout_seconds} secondi."
                ),
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile eseguire il comando: {error}"
                ),
            )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        if completed.returncode != 0:
            return ToolResult(
                success=False,
                output={
                    "returncode": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                error=(
                    f"Il comando è terminato con codice "
                    f"{completed.returncode}."
                ),
            )

        return ToolResult(
            success=True,
            output={
                "returncode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
from __future__ import annotations

import getpass
import os
import platform
import stat
from pathlib import Path
from typing import Any

from app.tools.application_resolver import (
    ApplicationResolver,
)
from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class DiscoverSystemInfoTool(Tool):
    """
    Restituisce informazioni generali ottenute dinamicamente dal sistema.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="discover_system_info",
            description=(
                "Scopre informazioni dinamiche sul sistema operativo "
                "e sull'ambiente di IRIS, senza usare valori hardcoded "
                "per descrivere il computer."
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
                error="discover_system_info non accetta argomenti.",
            )

        try:
            path_entries = [
                entry
                for entry in os.environ.get(
                    "PATH",
                    "",
                ).split(os.pathsep)
                if entry
            ]

            output = {
                "os": {
                    "name": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "python": platform.python_version(),
                },
                "host": {
                    "hostname": platform.node() or None,
                    "username": getpass.getuser() or None,
                    "home": str(Path.home()),
                    "cwd": os.getcwd(),
                    "temp_directory": str(Path(
                        os.environ.get(
                            "TEMP",
                            os.environ.get(
                                "TMPDIR",
                                "",
                            ),
                        )
                    )) if (
                        os.environ.get("TEMP")
                        or os.environ.get("TMPDIR")
                    ) else None,
                },
                "cpu_count": os.cpu_count(),
                "shell": (
                    os.environ.get("COMSPEC")
                    if os.name == "nt"
                    else os.environ.get("SHELL")
                ),
                "path_entries": path_entries,
                "environment_variable_names": sorted(
                    os.environ.keys(),
                    key=str.casefold,
                ),
                "user_message": (
                    "Ho rilevato dinamicamente sistema operativo, "
                    "computer, ambiente e percorsi di esecuzione."
                ),
            }

            return ToolResult(
                success=True,
                output=output,
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile leggere le informazioni di sistema: {error}"
                ),
            )


class DiscoverCommandsTool(Tool):
    """
    Scopre i comandi eseguibili realmente disponibili nel PATH.
    """

    def __init__(
        self,
        path_environment: str | None = None,
        pathext_environment: str | None = None,
    ) -> None:
        self.path_environment = (
            path_environment
            if path_environment is not None
            else os.environ.get("PATH", "")
        )

        self.pathext_environment = (
            pathext_environment
            if pathext_environment is not None
            else os.environ.get("PATHEXT", "")
        )

        self._definition = ToolDefinition(
            name="discover_commands",
            description=(
                "Scopre dinamicamente i programmi eseguibili disponibili "
                "nel PATH del sistema. Non usa una lista hardcoded di "
                "comandi consentiti."
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
                error="discover_commands non accetta argomenti.",
            )

        try:
            directories = [
                Path(entry).expanduser()
                for entry in self.path_environment.split(
                    os.pathsep
                )
                if entry
            ]

            extensions = [
                extension.casefold()
                for extension
                in self.pathext_environment.split(";")
                if extension
            ]

            found: dict[str, dict[str, Any]] = {}

            for directory in directories:
                try:
                    if not directory.is_dir():
                        continue

                    for entry in directory.iterdir():
                        try:
                            is_executable = (
                                entry.is_file()
                                and (
                                    os.name == "nt"
                                    or os.access(
                                        entry,
                                        os.X_OK,
                                    )
                                )
                            )
                        except OSError:
                            continue

                        if not is_executable:
                            continue

                        name = entry.name
                        normalized_name = name.casefold()

                        if os.name == "nt":
                            suffix = entry.suffix.casefold()

                            if extensions and suffix not in extensions:
                                continue

                            stem = entry.stem
                        else:
                            stem = name

                        key = stem.casefold()

                        if key not in found:
                            found[key] = {
                                "name": stem,
                                "path": str(
                                    entry.resolve(
                                        strict=False
                                    )
                                ),
                                "source_directory": str(
                                    directory.resolve(
                                        strict=False
                                    )
                                ),
                            }

                        # Mantiene anche eventuali versioni con nome differente.
                        _ = normalized_name

                except OSError:
                    continue

            commands = sorted(
                found.values(),
                key=lambda item: item["name"].casefold(),
            )

            return ToolResult(
                success=True,
                output={
                    "count": len(commands),
                    "commands": commands,
                    "user_message": (
                        f"Ho scoperto {len(commands)} programmi "
                        "eseguibili disponibili nel PATH."
                    ),
                },
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile scoprire i comandi disponibili: {error}"
                ),
            )


class DiscoverApplicationsTool(Tool):
    """
    Scopre le applicazioni disponibili usando il resolver del PC.
    """

    def __init__(
        self,
        resolver: ApplicationResolver | None = None,
    ) -> None:
        self.resolver = resolver or ApplicationResolver()

        self._definition = ToolDefinition(
            name="discover_applications",
            description=(
                "Scopre dinamicamente le applicazioni disponibili "
                "sul PC usando le fonti reali del sistema."
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
                error="discover_applications non accetta argomenti.",
            )

        try:
            applications = self.resolver.discover()

            result = [
                {
                    "name": application.name,
                    "target": application.target,
                    "source": application.source,
                    "app_id": application.app_id,
                }
                for application in applications
            ]

            return ToolResult(
                success=True,
                output={
                    "count": len(result),
                    "applications": result,
                    "user_message": (
                        f"Ho scoperto {len(result)} applicazioni "
                        "disponibili sul PC."
                    ),
                },
            )

        except (
            OSError,
            ValueError,
            TypeError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile scoprire le applicazioni: {error}"
                ),
            )


class ListProcessesTool(Tool):
    """
    Elenca dinamicamente tutti i processi attualmente rilevabili.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="list_processes",
            description=(
                "Elenca dinamicamente i processi attualmente in esecuzione "
                "rilevati dal sistema operativo."
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
                error="list_processes non accetta argomenti.",
            )

        try:
            processes = DiscoverPCStateTool(
                include_processes=True,
                max_processes=None,
            )._discover_processes()

            result = [
                {
                    "pid": process.pid,
                    "name": process.name,
                    "executable": process.executable,
                    "command_line": process.command_line,
                }
                for process in processes
            ]

            return ToolResult(
                success=True,
                output={
                    "count": len(result),
                    "processes": result,
                    "user_message": (
                        f"Ho rilevato {len(result)} processi "
                        "attualmente in esecuzione."
                    ),
                },
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile leggere i processi: {error}"
                ),
            )


__all__ = [
    "DiscoverSystemInfoTool",
    "DiscoverCommandsTool",
    "DiscoverApplicationsTool",
    "ListProcessesTool",
]

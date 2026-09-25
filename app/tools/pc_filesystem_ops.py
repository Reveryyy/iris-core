from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class OpenPathTool(Tool):
    """
    Apre un file o una directory usando l'applicazione predefinita del SO.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="open_path",
            description=(
                "Apre un file o una directory tramite il sistema operativo "
                "locale e verifica che il percorso esista prima dell'apertura."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Percorso del file o della directory da aprire."
                        ),
                    },
                },
                "required": [
                    "path",
                ],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset(
                {
                    Permission.GUI.value,
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
        path = arguments.get("path")

        if not isinstance(path, str):
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
            resolved = Path(path).expanduser().resolve(
                strict=False
            )

            if not resolved.exists():
                return ToolResult(
                    success=False,
                    error=(
                        f"Il percorso '{resolved}' non esiste."
                    ),
                )

            if os.name == "nt":
                os.startfile(str(resolved))
            elif hasattr(os, "startfile"):
                os.startfile(str(resolved))
            else:
                opener = (
                    "open"
                    if os.uname().sysname == "Darwin"
                    else "xdg-open"
                )
                import subprocess

                subprocess.Popen(
                    [opener, str(resolved)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            return ToolResult(
                success=True,
                output={
                    "path": str(resolved),
                    "type": (
                        "directory"
                        if resolved.is_dir()
                        else "file"
                        if resolved.is_file()
                        else "other"
                    ),
                    "user_message": (
                        f"Ho aperto '{resolved}'."
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
                    f"Impossibile aprire '{resolved}': {error}"
                ),
            )


class CreateDirectoryTool(Tool):
    """
    Crea una directory nel percorso richiesto.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="create_directory",
            description=(
                "Crea una directory nel percorso indicato, incluse "
                "le directory intermedie mancanti."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Percorso della directory da creare."
                        ),
                    },
                },
                "required": [
                    "path",
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
        path = arguments.get("path")

        if not isinstance(path, str):
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
            resolved = Path(path).expanduser().resolve(
                strict=False
            )

            resolved.mkdir(
                parents=True,
                exist_ok=True,
            )

            if not resolved.is_dir():
                return ToolResult(
                    success=False,
                    error=(
                        f"'{resolved}' non è una directory."
                    ),
                )

            return ToolResult(
                success=True,
                output={
                    "path": str(resolved),
                    "created_or_existing": True,
                    "user_message": (
                        f"La directory '{resolved}' è disponibile."
                    ),
                },
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile creare '{resolved}': {error}"
                ),
            )


class CopyPathTool(Tool):
    """
    Copia file o directory senza limitazioni artificiali sul percorso.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="copy_path",
            description=(
                "Copia un file o una directory dal percorso sorgente "
                "al percorso destinazione usando il filesystem reale."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": (
                            "Percorso sorgente."
                        ),
                    },
                    "destination": {
                        "type": "string",
                        "description": (
                            "Percorso destinazione."
                        ),
                    },
                },
                "required": [
                    "source",
                    "destination",
                ],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset(
                {
                    Permission.READ.value,
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
        source = arguments.get("source")
        destination = arguments.get("destination")

        if not isinstance(source, str):
            return ToolResult(
                success=False,
                error="source deve essere una stringa.",
            )

        if not isinstance(destination, str):
            return ToolResult(
                success=False,
                error="destination deve essere una stringa.",
            )

        source = source.strip()
        destination = destination.strip()

        if not source or not destination:
            return ToolResult(
                success=False,
                error="source e destination non possono essere vuoti.",
            )

        try:
            resolved_source = Path(source).expanduser().resolve(
                strict=True
            )
            resolved_destination = Path(destination).expanduser().resolve(
                strict=False
            )

            if not resolved_source.exists():
                return ToolResult(
                    success=False,
                    error=(
                        f"La sorgente '{resolved_source}' non esiste."
                    ),
                )

            if resolved_source.is_dir():
                shutil.copytree(
                    resolved_source,
                    resolved_destination,
                    dirs_exist_ok=True,
                )
            else:
                target = resolved_destination

                if (
                    resolved_destination.exists()
                    and resolved_destination.is_dir()
                ):
                    target = (
                        resolved_destination
                        / resolved_source.name
                    )

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.copy2(
                    resolved_source,
                    target,
                )

            return ToolResult(
                success=True,
                output={
                    "source": str(resolved_source),
                    "destination": str(resolved_destination),
                    "verified_destination_exists": (
                        resolved_destination.exists()
                    ),
                },
            )

        except (
            OSError,
            shutil.Error,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile copiare '{resolved_source}': {error}"
                ),
            )


class MovePathTool(Tool):
    """
    Sposta file o directory usando il filesystem reale.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="move_path",
            description=(
                "Sposta un file o una directory dal percorso sorgente "
                "al percorso destinazione."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": (
                            "Percorso sorgente."
                        ),
                    },
                    "destination": {
                        "type": "string",
                        "description": (
                            "Percorso destinazione."
                        ),
                    },
                },
                "required": [
                    "source",
                    "destination",
                ],
                "additionalProperties": False,
            },
            risk_level="medium",
            permissions=frozenset(
                {
                    Permission.READ.value,
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
        source = arguments.get("source")
        destination = arguments.get("destination")

        if not isinstance(source, str):
            return ToolResult(
                success=False,
                error="source deve essere una stringa.",
            )

        if not isinstance(destination, str):
            return ToolResult(
                success=False,
                error="destination deve essere una stringa.",
            )

        source = source.strip()
        destination = destination.strip()

        if not source or not destination:
            return ToolResult(
                success=False,
                error="source e destination non possono essere vuoti.",
            )

        resolved_source = Path(source).expanduser().resolve(
            strict=False
        )
        resolved_destination = Path(destination).expanduser().resolve(
            strict=False
        )

        try:
            if not resolved_source.exists():
                return ToolResult(
                    success=False,
                    error=(
                        f"La sorgente '{resolved_source}' non esiste."
                    ),
                )

            target = resolved_destination

            if (
                resolved_destination.exists()
                and resolved_destination.is_dir()
            ):
                target = (
                    resolved_destination
                    / resolved_source.name
                )

            shutil.move(
                str(resolved_source),
                str(target),
            )

            return ToolResult(
                success=True,
                output={
                    "source": str(resolved_source),
                    "destination": str(target),
                    "verified_destination_exists": target.exists(),
                    "verified_source_missing": not resolved_source.exists(),
                },
            )

        except (
            OSError,
            shutil.Error,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile spostare '{resolved_source}': {error}"
                ),
            )


__all__ = [
    "OpenPathTool",
    "CreateDirectoryTool",
    "CopyPathTool",
    "MovePathTool",
]

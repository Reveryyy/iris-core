from __future__ import annotations

import fnmatch
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


def _isoformat_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat()


def _find_git_root(path: Path) -> Path | None:
    current = path.expanduser().resolve(strict=False)

    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        git_marker = candidate / ".git"
        if git_marker.exists():
            return candidate

    return None


def _discover_git_tracked_paths(
    path: Path,
) -> tuple[Path, set[str]] | None:
    git_root = _find_git_root(path)

    if git_root is None:
        return None

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(git_root),
                "ls-files",
                "-z",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5.0,
        )
    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return None

    if completed.returncode != 0:
        return None

    tracked_paths = {
        item.replace("/", "\\").casefold()
        for item in completed.stdout.split("\x00")
        if item
    }

    return git_root, tracked_paths


def _is_git_tracked(
    path: Path,
    git_state: tuple[Path, set[str]] | None,
) -> bool | None:
    if git_state is None:
        return None

    git_root, tracked_paths = git_state

    try:
        relative = path.resolve(strict=False).relative_to(
            git_root.resolve(strict=False)
        )
    except ValueError:
        return None

    return relative.as_posix().replace("/", "\\").casefold() in tracked_paths


def _path_metadata(path: Path) -> dict[str, Any]:
    stat_result = path.stat()

    if path.is_dir():
        path_type = "directory"
    elif path.is_file():
        path_type = "file"
    elif path.is_symlink():
        path_type = "symlink"
    else:
        path_type = "other"

    return {
        "path": str(path),
        "name": path.name,
        "parent": str(path.parent),
        "type": path_type,
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_directory": path.is_dir(),
        "is_symlink": path.is_symlink(),
        "size_bytes": (
            stat_result.st_size
            if path.is_file()
            else None
        ),
        "modified_at": _isoformat_timestamp(
            stat_result.st_mtime
        ),
        "created_at": _isoformat_timestamp(
            getattr(
                stat_result,
                "st_ctime",
                stat_result.st_mtime,
            )
        ),
        "mode": stat.filemode(
            stat_result.st_mode
        ),
    }


class InspectPathTool(Tool):
    """
    Ispeziona dinamicamente qualsiasi percorso accessibile a IRIS.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="inspect_path",
            description=(
                "Ispeziona un percorso del filesystem accessibile a IRIS "
                "e restituisce informazioni dinamiche sul percorso, "
                "inclusi tipo, dimensione, tempi e proprietà."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Percorso assoluto o relativo da ispezionare."
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
            resolved_path = Path(path).expanduser().resolve(
                strict=False
            )

            if not resolved_path.exists():
                return ToolResult(
                    success=False,
                    output={
                        "path": str(resolved_path),
                        "exists": False,
                    },
                    error=(
                        f"Il percorso '{resolved_path}' non esiste."
                    ),
                )

            metadata = _path_metadata(
                resolved_path
            )

            return ToolResult(
                success=True,
                output={
                    **metadata,
                    "user_message": (
                        f"Ho ispezionato '{resolved_path}'."
                    ),
                },
            )

        except (
            OSError,
            ValueError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile ispezionare il percorso: {error}"
                ),
            )


class ListDirectoryTool(Tool):
    """
    Elenca il contenuto di una directory senza dipendere da nomi
    di cartelle predefiniti.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="list_directory",
            description=(
                "Elenca dinamicamente il contenuto di una directory "
                "accessibile a IRIS. Non richiede una lista di directory "
                "predefinita e può lavorare su qualsiasi percorso."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory da elencare."
                        ),
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": (
                            "Se true include anche file e cartelle "
                            "nascosti quando il filesystem li espone."
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
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        path = arguments.get("path")
        include_hidden = arguments.get(
            "include_hidden",
            True,
        )

        if not isinstance(path, str):
            return ToolResult(
                success=False,
                error="Il percorso deve essere una stringa.",
            )

        if not isinstance(include_hidden, bool):
            return ToolResult(
                success=False,
                error="include_hidden deve essere boolean.",
            )

        path = path.strip()

        if not path:
            return ToolResult(
                success=False,
                error="Il percorso non può essere vuoto.",
            )

        try:
            directory = Path(path).expanduser().resolve(
                strict=False
            )

            if not directory.exists():
                return ToolResult(
                    success=False,
                    error=(
                        f"La directory '{directory}' non esiste."
                    ),
                )

            if not directory.is_dir():
                return ToolResult(
                    success=False,
                    error=(
                        f"'{directory}' non è una directory."
                    ),
                )

            entries: list[dict[str, Any]] = []

            for entry in sorted(
                directory.iterdir(),
                key=lambda item: (
                    not item.is_dir(),
                    item.name.casefold(),
                ),
            ):
                if not include_hidden and entry.name.startswith("."):
                    continue

                try:
                    metadata = _path_metadata(
                        entry
                    )
                except OSError as error:
                    metadata = {
                        "path": str(entry),
                        "name": entry.name,
                        "type": "unreadable",
                        "error": str(error),
                    }

                entries.append(metadata)

            return ToolResult(
                success=True,
                output={
                    "path": str(directory),
                    "entries": entries,
                    "count": len(entries),
                    "user_message": (
                        f"Ho trovato {len(entries)} elementi "
                        f"in '{directory}'."
                    ),
                },
            )

        except (
            OSError,
            ValueError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile elencare la directory: {error}"
                ),
            )


class SearchFilesTool(Tool):
    """
    Cerca dinamicamente file e directory usando il filesystem reale.
    """

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="search_files",
            description=(
                "Cerca file e directory in modo ricorsivo a partire "
                "da un percorso indicato. Supporta una ricerca per "
                "nome con wildcard e non utilizza un elenco "
                "hardcoded di percorsi."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Nome o pattern da cercare. "
                            "Sono supportate wildcard come *.py."
                        ),
                    },
                    "location": {
                        "type": "string",
                        "description": (
                            "Directory dalla quale iniziare la ricerca."
                        ),
                    },
                    "include_directories": {
                        "type": "boolean",
                        "description": (
                            "Se true include anche le directory "
                            "nei risultati."
                        ),
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": (
                            "Se true mantiene la distinzione "
                            "tra maiuscole e minuscole."
                        ),
                    },
                },
                "required": [
                    "query",
                    "location",
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
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:
        query = arguments.get("query")
        location = arguments.get("location")
        include_directories = arguments.get(
            "include_directories",
            False,
        )
        case_sensitive = arguments.get(
            "case_sensitive",
            False,
        )

        if not isinstance(query, str):
            return ToolResult(
                success=False,
                error="query deve essere una stringa.",
            )

        if not isinstance(location, str):
            return ToolResult(
                success=False,
                error="location deve essere una stringa.",
            )

        if not isinstance(include_directories, bool):
            return ToolResult(
                success=False,
                error="include_directories deve essere boolean.",
            )

        if not isinstance(case_sensitive, bool):
            return ToolResult(
                success=False,
                error="case_sensitive deve essere boolean.",
            )

        query = query.strip()
        location = location.strip()

        if not query:
            return ToolResult(
                success=False,
                error="query non può essere vuota.",
            )

        if not location:
            return ToolResult(
                success=False,
                error="location non può essere vuota.",
            )

        try:
            root = Path(location).expanduser().resolve(
                strict=False
            )

            if not root.exists():
                return ToolResult(
                    success=False,
                    error=(
                        f"La directory '{root}' non esiste."
                    ),
                )

            if not root.is_dir():
                return ToolResult(
                    success=False,
                    error=(
                        f"'{root}' non è una directory."
                    ),
                )

            normalized_query = (
                query
                if case_sensitive
                else query.casefold()
            )

            results: list[dict[str, Any]] = []
            git_state = _discover_git_tracked_paths(root)

            for current_root, directories, files in os.walk(
                root,
                followlinks=False,
            ):
                current_path = Path(current_root)

                candidates = list(files)

                if include_directories:
                    candidates.extend(
                        directories
                    )

                for name in candidates:
                    comparison_name = (
                        name
                        if case_sensitive
                        else name.casefold()
                    )

                    matched = fnmatch.fnmatchcase(
                        comparison_name,
                        normalized_query,
                    )

                    if not matched:
                        continue

                    candidate = current_path / name

                    try:
                        metadata = _path_metadata(
                            candidate
                        )
                        metadata["is_git_tracked"] = _is_git_tracked(
                            candidate,
                            git_state,
                        )
                    except OSError as error:
                        metadata = {
                            "path": str(candidate),
                            "name": name,
                            "type": "unreadable",
                            "error": str(error),
                        }

                    results.append(
                        metadata
                    )

            results.sort(
                key=lambda item: item.get(
                    "path",
                    "",
                ).casefold()
            )

            return ToolResult(
                success=True,
                output={
                    "query": query,
                    "location": str(root),
                    "results": results,
                    "count": len(results),
                    "user_message": (
                        f"Ho trovato {len(results)} risultati "
                        f"per '{query}' in '{root}'."
                    ),
                },
            )

        except (
            OSError,
            ValueError,
        ) as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile cercare nel filesystem: {error}"
                ),
            )


__all__ = [
    "InspectPathTool",
    "ListDirectoryTool",
    "SearchFilesTool",
]

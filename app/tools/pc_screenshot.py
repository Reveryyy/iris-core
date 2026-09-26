from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ImageGrab

from app.tools.base import Tool, ToolDefinition
from app.tools.permissions import Permission
from app.tools.result import ToolResult


class ScreenshotTool(Tool):
    """
    Cattura lo schermo principale e salva lo screenshot
    in una directory dinamica; il percorso di output può essere specificato.
    """

    def __init__(
        self,
        default_directory: str | Path | None = None,
        allowed_root: str | Path | None = None,
    ) -> None:

        self.allowed_root = (
            Path(allowed_root).expanduser().resolve()
            if allowed_root is not None
            else None
        )

        if default_directory is None and self.allowed_root is not None:
            default_directory = self.allowed_root

        self.default_directory = (
            Path(default_directory).expanduser().resolve()
            if default_directory is not None
            else Path.cwd().resolve()
        )

        self._legacy_allowed_root_mode = (
            self.allowed_root is not None
        )

        if self._legacy_allowed_root_mode:
            input_schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
            description = (
                "Cattura lo schermo corrente e salva uno "
                "screenshot PNG nella directory autorizzata."
            )
        else:
            input_schema = {
                "type": "object",
                "properties": {
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Percorso completo del file PNG da creare. "
                            "Se omesso, viene usata la directory predefinita."
                        ),
                    },
                },
                "additionalProperties": False,
            }
            description = (
                "Cattura lo schermo corrente e salva uno "
                "screenshot PNG. Il percorso di output è opzionale."
            )

        self._definition = ToolDefinition(
            name="screenshot",
            description=description,
            input_schema=input_schema,
            risk_level="medium",
            permissions=frozenset(
                {
                    Permission.GUI.value,
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

        if not isinstance(arguments, dict):
            return ToolResult(
                success=False,
                error="Gli argomenti dello screenshot devono essere un oggetto.",
            )

        if self._legacy_allowed_root_mode:
            if arguments:
                return ToolResult(
                    success=False,
                    error="Il tool screenshot non accetta argomenti.",
                )
            output_path = None
        else:
            unknown_arguments = [
                key
                for key in arguments
                if key != "output_path"
            ]

            if unknown_arguments:
                return ToolResult(
                    success=False,
                    error=(
                        "Il tool screenshot non accetta argomenti "
                        "sconosciuti: "
                        + ", ".join(
                            map(str, unknown_arguments)
                        )
                    ),
                )

            output_path = arguments.get("output_path")

            if output_path is not None and not isinstance(output_path, str):
                return ToolResult(
                    success=False,
                    error="output_path deve essere una stringa.",
                )

        if isinstance(output_path, str) and output_path.strip():
            screenshot_path = (
                Path(output_path)
                .expanduser()
                .resolve(strict=False)
            )
            screenshots_directory = screenshot_path.parent
        else:
            screenshots_directory = self.default_directory / "screenshots"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_path = (
                screenshots_directory / f"iris_{timestamp}.png"
            ).resolve(strict=False)

        if self.allowed_root is not None:
            try:
                screenshot_path.relative_to(
                    self.allowed_root
                )
            except ValueError:
                return ToolResult(
                    success=False,
                    error=(
                        "Il percorso dello screenshot si trova "
                        "fuori dalla directory autorizzata."
                    ),
                )

        try:
            screenshots_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile creare la directory "
                    f"degli screenshot: {error}"
                ),
            )

        try:
            image = ImageGrab.grab(
                all_screens=True
            )

            image.save(
                screenshot_path,
                format="PNG",
            )

        except OSError as error:
            return ToolResult(
                success=False,
                error=(
                    f"Impossibile catturare lo screenshot: {error}"
                ),
            )

        except Exception as error:
            return ToolResult(
                success=False,
                error=(
                    "Errore durante la cattura dello screenshot: "
                    f"{error}"
                ),
            )

        try:
            file_size = screenshot_path.stat().st_size
        except OSError:
            file_size = 0

        return ToolResult(
            success=True,
            output={
                "path": str(screenshot_path),
                "format": "png",
                "bytes": file_size,
            },
        )


__all__ = [
    "ScreenshotTool",
]
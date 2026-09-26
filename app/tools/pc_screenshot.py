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
    ) -> None:

        self.default_directory = (
            Path(default_directory).expanduser().resolve()
            if default_directory is not None
            else Path.cwd().resolve()
        )

        self._definition = ToolDefinition(
            name="screenshot",
            description=(
                "Cattura lo schermo corrente e salva uno "
                "screenshot PNG. Il percorso di output è opzionale."
            ),
            input_schema={
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
            },
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

        output_path = arguments.get("output_path")

        if output_path is not None and not isinstance(output_path, str):
            return ToolResult(
                success=False,
                error="output_path deve essere una stringa.",
            )

        if isinstance(output_path, str) and output_path.strip():
            screenshot_path = Path(output_path).expanduser().resolve(strict=False)
            screenshots_directory = screenshot_path.parent
        else:
            screenshots_directory = self.default_directory / "screenshots"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_path = (
                screenshots_directory / f"iris_{timestamp}.png"
            ).resolve(strict=False)

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
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
    esclusivamente nella directory autorizzata del PC Agent.
    """

    def __init__(
        self,
        allowed_root: str | Path | None = None,
    ) -> None:

        self.allowed_root = (
            Path(
                allowed_root
                or Path.cwd()
            )
            .resolve()
        )

        self._definition = ToolDefinition(
            name="screenshot",
            description=(
                "Cattura lo schermo corrente e salva uno "
                "screenshot PNG nella directory autorizzata."
            ),
            input_schema={
                "type": "object",
                "properties": {},
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

        if arguments:
            return ToolResult(
                success=False,
                error=(
                    "Il tool screenshot non accetta argomenti."
                ),
            )

        screenshots_directory = (
            self.allowed_root
            / "screenshots"
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

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        screenshot_path = (
            screenshots_directory
            / f"iris_{timestamp}.png"
        ).resolve()

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
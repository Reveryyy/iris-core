from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolDefinition
from app.tools.pc import (
    OpenApplicationTool,
    ReadFileTool,
    RunCommandTool,
    WriteFileTool,
)
from app.tools.pc_gui import TypeTextTool
from app.tools.pc_mouse import ClickMouseTool
from app.tools.pc_screenshot import ScreenshotTool
from app.tools.pc_state import GetForegroundWindowTool
from app.tools.pc_window import FocusWindowTool
from app.tools.result import ToolResult


class EchoTool(Tool):

    def __init__(self) -> None:

        self._definition = ToolDefinition(
            name="echo",
            description=(
                "Restituisce il testo ricevuto."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                    },
                },
                "required": [
                    "text",
                ],
                "additionalProperties": False,
            },
            risk_level="none",
            permissions=frozenset(),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
    ) -> ToolResult:

        text = arguments.get(
            "text"
        )

        if not isinstance(
            text,
            str,
        ):
            return ToolResult(
                success=False,
                error=(
                    "L'argomento 'text' deve essere "
                    "una stringa."
                ),
            )

        return ToolResult(
            success=True,
            output=text,
        )


__all__ = [
    "EchoTool",
    "OpenApplicationTool",
    "ReadFileTool",
    "WriteFileTool",
    "RunCommandTool",
    "FocusWindowTool",
    "ScreenshotTool",
    "TypeTextTool",
    "ClickMouseTool",
    "GetForegroundWindowTool",
]
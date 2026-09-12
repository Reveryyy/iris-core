from __future__ import annotations

from typing import Any

from app.tools.base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
            self,
            tool: Tool,
    ) -> None:

        name = tool.definition.name

        if name in self._tools:
            raise ValueError(
                f"Tool già registrato: {name}"
            )

        self._tools[name] = tool

    def get(
            self,
            name: str,
    ) -> Tool | None:

        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(
            self._tools.values()
        )

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.definition.name,
                "description": tool.definition.description,
                "input_schema": tool.definition.input_schema,
                "risk_level": tool.definition.risk_level,
                "permissions": sorted(
                    permission
                    for permission
                    in tool.definition.permissions
                ),
            }
            for tool in self._tools.values()
        ]
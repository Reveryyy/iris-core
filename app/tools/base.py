from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: str
    permissions: frozenset[str]


class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        raise NotImplementedError

    @abstractmethod
    def execute(
            self,
            arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError
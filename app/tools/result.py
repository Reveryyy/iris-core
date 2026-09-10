from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: Any = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise TypeError(
                "Il campo 'success' deve essere booleano."
            )

        if self.success and self.error is not None:
            raise ValueError(
                "Un risultato riuscito non può contenere un errore."
            )

        if not self.success and self.error is None:
            raise ValueError(
                "Un risultato fallito deve contenere un errore."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }

    @classmethod
    def from_dict(
            cls,
            data: dict[str, Any],
    ) -> "ToolResult":

        if not isinstance(data, dict):
            raise TypeError(
                "Il ToolResult deve essere un dizionario."
            )

        if "success" not in data:
            raise ValueError(
                "Il ToolResult deve contenere 'success'."
            )

        return cls(
            success=data["success"],
            output=data.get("output"),
            error=data.get("error"),
        )
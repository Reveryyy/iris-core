from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentObservation:
    step_index: int
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    output: Any = None
    error: str | None = None
    verified: bool = False
    verification_reason: str = ""

    def __post_init__(self) -> None:
        if self.step_index <= 0:
            raise ValueError(
                "step_index deve essere maggiore di zero."
            )

        if not isinstance(
            self.tool_name,
            str,
        ):
            raise TypeError(
                "Il nome del tool deve essere una stringa."
            )

        if not self.tool_name.strip():
            raise ValueError(
                "Il nome del tool non può essere vuoto."
            )

        if not isinstance(
            self.arguments,
            dict,
        ):
            raise TypeError(
                "Gli argomenti devono essere un dizionario."
            )

        if not isinstance(
            self.success,
            bool,
        ):
            raise TypeError(
                "success deve essere booleano."
            )

        if not isinstance(
            self.verified,
            bool,
        ):
            raise TypeError(
                "verified deve essere booleano."
            )

        if not isinstance(
            self.verification_reason,
            str,
        ):
            raise TypeError(
                "La motivazione della verifica deve essere una stringa."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "verified": self.verified,
            "verification_reason": self.verification_reason,
        }

    def to_context(self) -> str:
        lines = [
            f"STEP {self.step_index}",
            f"Tool: {self.tool_name}",
            f"Argomenti: {self.arguments}",
            f"Successo: {self.success}",
            f"Verificato: {self.verified}",
        ]

        if self.output is not None:
            lines.append(
                f"Output: {self.output}"
            )

        if self.error:
            lines.append(
                f"Errore: {self.error}"
            )

        if self.verification_reason:
            lines.append(
                f"Verifica: {self.verification_reason}"
            )

        return "\n".join(
            lines
        )
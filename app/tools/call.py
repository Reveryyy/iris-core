from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(
                "Il nome del tool deve essere una stringa."
            )

        if not self.name.strip():
            raise ValueError(
                "Il nome del tool non può essere vuoto."
            )

        if not isinstance(self.arguments, dict):
            raise TypeError(
                "Gli argomenti del tool devono essere un dizionario."
            )

        if (
            self.call_id is not None
            and not isinstance(self.call_id, str)
        ):
            raise TypeError(
                "Il call_id deve essere una stringa."
            )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "arguments": self.arguments,
        }

        if self.call_id is not None:
            data["call_id"] = self.call_id

        return data

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "ToolCall":

        if not isinstance(data, dict):
            raise TypeError(
                "La tool call deve essere un dizionario."
            )

        name = data.get("name")
        arguments = data.get("arguments")
        call_id = data.get("call_id")

        if not isinstance(name, str):
            raise ValueError(
                "La tool call deve contenere un nome valido."
            )

        if not isinstance(arguments, dict):
            raise ValueError(
                "La tool call deve contenere "
                "un dizionario di argomenti."
            )

        if (
            call_id is not None
            and not isinstance(call_id, str)
        ):
            raise ValueError(
                "Il call_id deve essere una stringa."
            )

        return cls(
            name=name,
            arguments=arguments,
            call_id=call_id,
        )
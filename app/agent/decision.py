from dataclasses import dataclass
from enum import Enum


class AgentDecision(str, Enum):
    DONE = "done"
    CONTINUE = "continue"
    ASK_USER = "ask_user"


@dataclass(frozen=True)
class AgentDecisionResult:
    decision: AgentDecision
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.decision,
            AgentDecision,
        ):
            raise TypeError(
                "La decisione dell'agente deve essere "
                "un'istanza di AgentDecision."
            )

        if (
            self.message is not None
            and not isinstance(
                self.message,
                str,
            )
        ):
            raise TypeError(
                "Il messaggio della decisione deve essere "
                "una stringa oppure None."
            )
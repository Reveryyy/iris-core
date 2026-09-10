from dataclasses import dataclass

from app.tools.result import ToolResult


@dataclass(frozen=True)
class AgentVerification:
    verified: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.verified,
            bool,
        ):
            raise TypeError(
                "verified deve essere booleano."
            )

        if not isinstance(
            self.reason,
            str,
        ):
            raise TypeError(
                "La motivazione della verifica deve essere una stringa."
            )


class AgentVerifier:
    """
    Verifica un risultato prodotto da un tool.

    In questa prima versione:
    - success=True -> risultato verificato;
    - success=False -> risultato non verificato;
    - se viene fornito un criterio di successo testuale,
      viene usato per documentare la verifica ma non
      interpretato semanticamente dal codice.

    La verifica semantica avanzata verrà aggiunta più avanti
    senza bypassare il risultato reale del tool.
    """

    def verify(
        self,
        result: ToolResult,
        success_criteria: str | None = None,
    ) -> AgentVerification:

        if not isinstance(
            result,
            ToolResult,
        ):
            raise TypeError(
                "Il risultato da verificare deve essere un ToolResult."
            )

        if result.success:
            if success_criteria:
                return AgentVerification(
                    verified=True,
                    reason=(
                        "Il tool ha restituito success=true. "
                        f"Criterio dichiarato: {success_criteria}"
                    ),
                )

            return AgentVerification(
                verified=True,
                reason=(
                    "Il tool ha restituito success=true."
                ),
            )

        error = result.error or (
            "Il tool ha restituito un errore."
        )

        return AgentVerification(
            verified=False,
            reason=(
                "Il risultato non è verificato perché "
                f"il tool ha fallito: {error}"
            ),
        )
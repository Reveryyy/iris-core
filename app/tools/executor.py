
from app.tools.call import ToolCall
from app.tools.dispatcher import ToolDispatcher
from app.tools.parser import ToolCallParser
from app.tools.result import ToolResult


class ToolExecutionService:
    """
    Livello centrale di esecuzione dei tool.

    Responsabilità:
    - parsing;
    - dispatch;
    - gestione degli errori;
    - protezione dalle eccezioni interne.
    """

    def __init__(
            self,
            dispatcher: ToolDispatcher,
            parser: ToolCallParser | None = None,
    ):
        self.dispatcher = dispatcher
        self.parser = parser or ToolCallParser()

    def execute_response(
            self,
            response: str,
            confirmed: bool = False,
    ) -> ToolResult:

        try:
            _, tool_call = (
                self.parser.parse_response(
                    response
                )
            )
        except (TypeError, ValueError) as error:
            return ToolResult(
                success=False,
                error=str(error),
            )

        if tool_call is None:
            return ToolResult(
                success=False,
                error=(
                    "La risposta del modello "
                    "non contiene una tool call."
                ),
            )

        return self.execute_call(
            tool_call=tool_call,
            confirmed=confirmed,
        )

    def execute_call(
            self,
            tool_call: ToolCall,
            confirmed: bool = False,
    ) -> ToolResult:

        try:
            return self.dispatcher.dispatch(
                tool_call=tool_call,
                confirmed=confirmed,
            )

        except (
            TypeError,
            ValueError,
            PermissionError,
        ) as error:
            return ToolResult(
                success=False,
                error=str(error),
            )

        except Exception:
            return ToolResult(
                success=False,
                error=(
                    "Errore interno durante "
                    "l'esecuzione del tool."
                ),
            )


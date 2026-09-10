
from dataclasses import dataclass

from app.tools.call import ToolCall
from app.tools.executor import ToolExecutionService
from app.tools.result import ToolResult


@dataclass(frozen=True)
class CoreToolResponse:
    is_tool_call: bool
    response: str | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    protocol_error: str | None = None


class CoreToolHandler:
    def __init__(
            self,
            execution_service: ToolExecutionService,
    ):
        self.execution_service = execution_service

    def handle_response(
            self,
            response: str,
            confirmed: bool = False,
    ) -> CoreToolResponse:

        try:
            content, tool_call = (
                self.execution_service.parser.parse_response(
                    response
                )
            )

        except (TypeError, ValueError) as error:
            return CoreToolResponse(
                is_tool_call=False,
                protocol_error=str(error),
            )

        if tool_call is None:
            return CoreToolResponse(
                is_tool_call=False,
                response=content,
            )

        result = self.execution_service.execute_call(
            tool_call=tool_call,
            confirmed=confirmed,
        )

        return CoreToolResponse(
            is_tool_call=True,
            tool_call=tool_call,
            tool_result=result,
        )


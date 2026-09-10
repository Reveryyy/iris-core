
from app.tools.base import Tool
from app.tools.call import ToolCall
from app.tools.core import CoreToolHandler
from app.tools.dispatcher import ToolDispatcher
from app.tools.executor import ToolExecutionService
from app.tools.parser import ToolCallParser
from app.tools.permissions import PermissionManager
from app.tools.registry import ToolRegistry
from app.tools.result import ToolResult
from app.tools.validator import ToolSchemaValidator


class ToolSystem:
    """
    Facade principale del Tool System di IRIS.

    Mantiene centralizzati:
    - Registry
    - Permission Manager
    - Schema Validator
    - Parser
    - Dispatcher
    - Executor
    - Core handler
    """

    def __init__(
            self,
            registry: ToolRegistry | None = None,
            permissions: PermissionManager | None = None,
            validator: ToolSchemaValidator | None = None,
            parser: ToolCallParser | None = None,
    ):
        self.registry = registry or ToolRegistry()
        self.permissions = (
            permissions
            or PermissionManager()
        )
        self.validator = (
            validator
            or ToolSchemaValidator()
        )
        self.parser = parser or ToolCallParser()

        self.dispatcher = ToolDispatcher(
            registry=self.registry,
            permissions=self.permissions,
            validator=self.validator,
        )

        self.executor = ToolExecutionService(
            dispatcher=self.dispatcher,
            parser=self.parser,
        )

        self.core_handler = CoreToolHandler(
            execution_service=self.executor,
        )

    def register(
            self,
            tool: Tool,
    ) -> None:
        self.registry.register(tool)

    def execute(
            self,
            tool_call: ToolCall,
            confirmed: bool = False,
    ) -> ToolResult:

        return self.executor.execute_call(
            tool_call=tool_call,
            confirmed=confirmed,
        )

    def execute_response(
            self,
            response: str,
            confirmed: bool = False,
    ) -> ToolResult:

        return self.executor.execute_response(
            response=response,
            confirmed=confirmed,
        )

    def handle_core_response(
            self,
            response: str,
            confirmed: bool = False,
    ):
        return self.core_handler.handle_response(
            response=response,
            confirmed=confirmed,
        )

    def definitions(self) -> list[dict]:
        return self.registry.definitions()


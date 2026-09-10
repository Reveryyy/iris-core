from app.tools.call import ToolCall
from app.tools.permissions import Permission, PermissionManager
from app.tools.registry import ToolRegistry
from app.tools.result import ToolResult
from app.tools.validator import ToolSchemaValidator


class ToolDispatcher:
    def __init__(
            self,
            registry: ToolRegistry,
            permissions: PermissionManager,
            validator: ToolSchemaValidator | None = None,
    ):
        self.registry = registry
        self.permissions = permissions
        self.validator = validator or ToolSchemaValidator()

    def dispatch(
            self,
            tool_call: ToolCall,
            confirmed: bool = False,
    ) -> ToolResult:

        tool = self.registry.get(
            tool_call.name
        )

        if tool is None:
            raise ValueError(
                f"Tool non trovato: {tool_call.name}"
            )

        self.validator.validate(
            definition=tool.definition,
            arguments=tool_call.arguments,
        )

        required_permissions = {
            Permission(permission)
            for permission
            in tool.definition.permissions
        }

        self.permissions.authorize(
            required=required_permissions,
            confirmed=confirmed,
        )

        return tool.execute(
            tool_call.arguments
        )
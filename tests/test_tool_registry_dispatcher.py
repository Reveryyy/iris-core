from typing import Any

import pytest

from app.tools import (
    CoreToolHandler,
    EchoTool,
    Permission,
    PermissionManager,
    Tool,
    ToolCall,
    ToolDefinition,
    ToolDispatcher,
    ToolExecutionService,
    ToolRegistry,
    ToolResult,
)


class RecordingTool(Tool):
    def __init__(self, name="record", permissions=frozenset(), risk="low"):
        self.calls = []
        self._name = name
        self._permissions = permissions
        self._risk = risk

    @property
    def definition(self):
        return ToolDefinition(
            name=self._name,
            description="Recording tool.",
            input_schema={
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
            risk_level=self._risk,
            permissions=self._permissions,
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append(arguments.copy())
        return ToolResult(
            success=True,
            output=arguments.get("value", "ok"),
        )


class BrokenTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            name="broken",
            description="Broken tool.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk_level="low",
            permissions=frozenset(),
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise RuntimeError("boom")


def test_registry_registers_and_retrieves_tools():
    registry = ToolRegistry()
    tool = RecordingTool()

    registry.register(tool)

    assert registry.get("record") is tool
    assert registry.list() == [tool]


def test_registry_rejects_duplicate_tool_names():
    registry = ToolRegistry()

    registry.register(RecordingTool())

    with pytest.raises(ValueError, match="Tool già registrato: record"):
        registry.register(RecordingTool())


def test_registry_returns_none_for_unknown_tool():
    registry = ToolRegistry()

    assert registry.get("missing") is None


def test_registry_definitions_expose_contract():
    registry = ToolRegistry()
    registry.register(RecordingTool())

    definitions = registry.definitions()

    assert definitions == [
        {
            "name": "record",
            "description": "Recording tool.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
            "risk_level": "low",
            "permissions": [],
        }
    ]


def test_dispatcher_executes_registered_tool():
    registry = ToolRegistry()
    tool = RecordingTool()
    registry.register(tool)

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(),
    )

    result = dispatcher.dispatch(
        ToolCall(
            name="record",
            arguments={"value": "hello"},
        )
    )

    assert result.success is True
    assert result.output == "hello"
    assert tool.calls == [{"value": "hello"}]


def test_dispatcher_rejects_unknown_tool():
    dispatcher = ToolDispatcher(
        registry=ToolRegistry(),
        permissions=PermissionManager(),
    )

    with pytest.raises(ValueError, match="Tool non trovato: missing"):
        dispatcher.dispatch(
            ToolCall(
                name="missing",
                arguments={},
            )
        )


def test_dispatcher_validates_arguments_before_execution():
    registry = ToolRegistry()
    tool = RecordingTool()
    registry.register(tool)

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(),
    )

    with pytest.raises(ValueError, match="Argomenti non consentiti"):
        dispatcher.dispatch(
            ToolCall(
                name="record",
                arguments={"unexpected": "x"},
            )
        )

    assert tool.calls == []


def test_dispatcher_requires_confirmation_for_delete():
    registry = ToolRegistry()
    registry.register(
        RecordingTool(
            name="delete_test",
            permissions=frozenset({Permission.DELETE.value}),
            risk="high",
        )
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(
            granted={Permission.DELETE},
        ),
    )

    with pytest.raises(PermissionError, match="conferma esplicita"):
        dispatcher.dispatch(
            ToolCall(
                name="delete_test",
                arguments={},
            ),
            confirmed=False,
        )


def test_dispatcher_allows_confirmed_delete():
    registry = ToolRegistry()
    tool = RecordingTool(
        name="delete_test",
        permissions=frozenset({Permission.DELETE.value}),
        risk="high",
    )
    registry.register(tool)

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(
            granted={Permission.DELETE},
        ),
    )

    result = dispatcher.dispatch(
        ToolCall(
            name="delete_test",
            arguments={},
        ),
        confirmed=True,
    )

    assert result.success is True
    assert result.output == "ok"
    assert tool.calls == [{}]


def test_execution_service_converts_dispatch_errors_to_tool_result():
    registry = ToolRegistry()
    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(),
    )

    service = ToolExecutionService(
        dispatcher=dispatcher,
    )

    result = service.execute_call(
        ToolCall(
            name="missing",
            arguments={},
        )
    )

    assert result.success is False
    assert "Tool non trovato" in result.error


def test_execution_service_protects_internal_tool_exceptions():
    registry = ToolRegistry()
    registry.register(BrokenTool())

    service = ToolExecutionService(
        dispatcher=ToolDispatcher(
            registry=registry,
            permissions=PermissionManager(),
        )
    )

    result = service.execute_call(
        ToolCall(
            name="broken",
            arguments={},
        )
    )

    assert result.success is False
    assert result.error == (
        "Errore interno durante l'esecuzione del tool."
    )


def test_execution_service_returns_structured_result_for_valid_call():
    registry = ToolRegistry()
    registry.register(EchoTool())

    service = ToolExecutionService(
        dispatcher=ToolDispatcher(
            registry=registry,
            permissions=PermissionManager(),
        )
    )

    result = service.execute_call(
        ToolCall(
            name="echo",
            arguments={"text": "ciao"},
        )
    )

    assert result == ToolResult(
        success=True,
        output="ciao",
    )


def test_core_tool_handler_preserves_tool_result():
    registry = ToolRegistry()
    registry.register(EchoTool())

    handler = CoreToolHandler(
        ToolExecutionService(
            dispatcher=ToolDispatcher(
                registry=registry,
                permissions=PermissionManager(),
            )
        )
    )

    response = handler.handle_response(
        response='''
        {
            "type": "tool_call",
            "content": null,
            "name": "echo",
            "arguments": {
                "text": "ciao"
            }
        }
        ''',
    )

    assert response.is_tool_call is True
    assert response.tool_call is not None
    assert response.tool_call.name == "echo"
    assert response.tool_result == ToolResult(
        success=True,
        output="ciao",
    )


def test_core_tool_handler_reports_unknown_tool_as_result():
    handler = CoreToolHandler(
        ToolExecutionService(
            dispatcher=ToolDispatcher(
                registry=ToolRegistry(),
                permissions=PermissionManager(),
            )
        )
    )

    response = handler.handle_response(
        response='''
        {
            "type": "tool_call",
            "content": null,
            "name": "missing",
            "arguments": {}
        }
        ''',
    )

    assert response.is_tool_call is True
    assert response.tool_result is not None
    assert response.tool_result.success is False
    assert "Tool non trovato" in response.tool_result.error

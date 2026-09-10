import json
from typing import Any

from app.core import IRISCore
from app.llm.router import LLMRouter
from app.tools import (
    CoreToolHandler,
    EchoTool,
    Permission,
    PermissionManager,
    Tool,
    ToolDefinition,
    ToolDispatcher,
    ToolExecutionService,
    ToolRegistry,
    ToolResult,
)


class FakeMemory:

    def search_semantic(
        self,
        message: str,
        limit: int = 5,
    ):
        return []

    def search_by_type(
        self,
        memory_type: str,
    ):
        return []

    def remember(
        self,
        content: str,
        memory_type: str,
        importance: int,
        confidence: float,
        source: str,
    ):
        return None

    def recall(
        self,
        memory_id: int,
    ):
        return None


class FakeRouterProvider:

    def __init__(
        self,
        responses: list[str],
    ):
        self.responses = list(
            responses
        )

        self.calls: list[
            dict[str, Any]
        ] = []

        self.call_counter = 0

    def generate(
        self,
        messages,
        max_tokens=512,
        temperature=0.2,
        response_format=None,
        tools=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
                "tools": tools,
            }
        )

        if not self.responses:
            raise AssertionError(
                "FakeRouterProvider ha ricevuto "
                "più chiamate di quelle previste."
            )

        response = self.responses.pop(
            0
        )

        try:
            data = json.loads(
                response.strip()
            )
        except json.JSONDecodeError:
            return response

        if (
            isinstance(data, dict)
            and data.get("type") == "tool_call"
            and not data.get("call_id")
        ):
            self.call_counter += 1

            data["call_id"] = (
                f"test_call_{self.call_counter}"
            )

            return json.dumps(
                data,
                ensure_ascii=False,
            )

        return response


def disable_memory_extraction(
    core: IRISCore,
) -> None:
    core.memory_extractor.extract = (
        lambda message: []
    )


def create_core(
    responses: list[str],
):

    provider = FakeRouterProvider(
        responses
    )

    router = LLMRouter(
        providers=[
            provider
        ]
    )

    registry = ToolRegistry()

    registry.register(
        EchoTool()
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(),
    )

    execution_service = ToolExecutionService(
        dispatcher=dispatcher
    )

    tool_handler = CoreToolHandler(
        execution_service=execution_service
    )

    core = IRISCore(
        router=router,
        memory=FakeMemory(),
        tool_handler=tool_handler,
    )

    disable_memory_extraction(
        core
    )

    return core, provider


def get_tool_calls(
    provider: FakeRouterProvider,
):
    return [
        call
        for call in provider.calls
        if call["tools"] is not None
    ]


def get_tool_messages(
    call: dict[str, Any],
):
    result = []

    for message in call["messages"]:

        if message.get("role") == "tool":
            result.append(
                message
            )

        tool_responses = message.get(
            "tool_responses"
        )

        if isinstance(
            tool_responses,
            list,
        ):
            result.extend(
                tool_responses
            )

    return result


def test_core_executes_structured_tool_call():

    core, provider = create_core(
        [
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "echo",
                "arguments": {
                    "text": "Ciao dal tool"
                }
            }
            """,
            """
            {
                "type": "final",
                "content": "Ciao dal tool",
                "name": null,
                "arguments": {}
            }
            """,
        ]
    )

    result = core.chat(
        "Usa il tool echo."
    )

    assert result == "Ciao dal tool"

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 2

    first_call = tool_calls[0]

    assert (
        first_call["response_format"]
        is None
    )

    assert first_call["tools"]

    assert any(
        tool["function"]["name"] == "echo"
        for tool in first_call["tools"]
    )

    system_message = first_call[
        "messages"
    ][0]

    assert (
        "REGOLE TOOL"
        in system_message["content"]
    )

    second_call = tool_calls[1]

    tool_messages = get_tool_messages(
        second_call
    )

    assert tool_messages

    assert any(
        (
            message.get("response")
            == {
                "success": True,
                "output": "Ciao dal tool",
                "error": None,
            }
        )
        or (
            "Ciao dal tool"
            in str(message)
        )
        for message in tool_messages
    )


def test_core_accepts_structured_final_response():

    core, provider = create_core(
        [
            """
            {
                "type": "final",
                "content": "Risposta normale.",
                "name": null,
                "arguments": {}
            }
            """
        ]
    )

    result = core.chat(
        "Ciao IRIS."
    )

    assert result == "Risposta normale."

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 1

    first_call = tool_calls[0]

    assert first_call["tools"]

    assert (
        first_call["response_format"]
        is None
    )


def test_core_rejects_unknown_tool():

    core, provider = create_core(
        [
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "accendi_tv",
                "arguments": {}
            }
            """,
            """
            {
                "type": "final",
                "content": "Il tool accendi_tv non è disponibile.",
                "name": null,
                "arguments": {}
            }
            """,
        ]
    )

    result = core.chat(
        "Usa il tool accendi_tv."
    )

    assert (
        "accendi_tv"
        in result
    )

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 2

    second_call = tool_calls[1]

    tool_messages = get_tool_messages(
        second_call
    )

    assert tool_messages

    assert any(
        "Tool non trovato"
        in str(message)
        for message in tool_messages
    )


def test_core_rejects_missing_tool_argument():

    core, provider = create_core(
        [
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "echo",
                "arguments": {}
            }
            """,
            """
            {
                "type": "final",
                "content": "Manca l'argomento obbligatorio.",
                "name": null,
                "arguments": {}
            }
            """,
        ]
    )

    result = core.chat(
        "Usa echo senza testo."
    )

    assert (
        "Manca l'argomento"
        in result
    )

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 2

    second_call = tool_calls[1]

    tool_messages = get_tool_messages(
        second_call
    )

    assert tool_messages

    assert any(
        "Argomento obbligatorio mancante: text"
        in str(message)
        for message in tool_messages
    )


def test_core_cannot_reuse_previous_tool_result():

    core, provider = create_core(
        [
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "echo",
                "arguments": {
                    "text": "Ciao dal tool"
                }
            }
            """,
            """
            {
                "type": "final",
                "content": "Primo risultato: Ciao dal tool",
                "name": null,
                "arguments": {}
            }
            """,
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "echo",
                "arguments": {}
            }
            """,
            """
            {
                "type": "final",
                "content": "Per questa chiamata manca il testo.",
                "name": null,
                "arguments": {}
            }
            """,
        ]
    )

    first_result = core.chat(
        "Usa echo."
    )

    assert first_result == (
        "Primo risultato: Ciao dal tool"
    )

    second_result = core.chat(
        "Usa echo senza testo."
    )

    assert second_result == (
        "Per questa chiamata manca il testo."
    )

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 4

    second_tool_exchange = tool_calls[
        3
    ]

    tool_messages = get_tool_messages(
        second_tool_exchange
    )

    assert tool_messages

    assert any(
        "Argomento obbligatorio mancante: text"
        in str(message)
        for message in tool_messages
    )


def test_core_sensitive_action_still_requires_confirmation():

    class DeleteTool(Tool):

        @property
        def definition(
            self,
        ):

            return ToolDefinition(
                name="delete_test",
                description="Delete.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                risk_level="high",
                permissions=frozenset(
                    {
                        Permission.DELETE.value,
                    }
                ),
            )

        def execute(
            self,
            arguments: dict[str, Any],
        ) -> ToolResult:

            return ToolResult(
                success=True,
                output="deleted",
            )

    provider = FakeRouterProvider(
        [
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "delete_test",
                "arguments": {}
            }
            """,
            """
            {
                "type": "final",
                "content": "Serve conferma esplicita.",
                "name": null,
                "arguments": {}
            }
            """,
        ]
    )

    router = LLMRouter(
        providers=[
            provider
        ]
    )

    registry = ToolRegistry()

    registry.register(
        DeleteTool()
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(
            granted={
                Permission.DELETE,
            }
        ),
    )

    core = IRISCore(
        router=router,
        memory=FakeMemory(),
        tool_handler=CoreToolHandler(
            ToolExecutionService(
                dispatcher=dispatcher
            )
        ),
    )

    disable_memory_extraction(
        core
    )

    result = core.chat(
        "Cancella il dato."
    )

    assert (
        "conferma esplicita"
        in result
    )

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 2

    tool_messages = get_tool_messages(
        tool_calls[1]
    )

    assert tool_messages

    assert any(
        "conferma esplicita"
        in str(message)
        for message in tool_messages
    )


def test_core_allows_confirmed_sensitive_action():

    class DeleteTool(Tool):

        @property
        def definition(
            self,
        ):

            return ToolDefinition(
                name="delete_test",
                description="Delete.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                risk_level="high",
                permissions=frozenset(
                    {
                        Permission.DELETE.value
                    }
                ),
            )

        def execute(
            self,
            arguments: dict[str, Any],
        ) -> ToolResult:

            return ToolResult(
                success=True,
                output="deleted",
            )

    provider = FakeRouterProvider(
        [
            """
            {
                "type": "tool_call",
                "content": null,
                "name": "delete_test",
                "arguments": {}
            }
            """,
            """
            {
                "type": "final",
                "content": "deleted",
                "name": null,
                "arguments": {}
            }
            """,
        ]
    )

    router = LLMRouter(
        providers=[
            provider
        ]
    )

    registry = ToolRegistry()

    registry.register(
        DeleteTool()
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(
            granted={
                Permission.DELETE
            }
        ),
    )

    core = IRISCore(
        router=router,
        memory=FakeMemory(),
        tool_handler=CoreToolHandler(
            ToolExecutionService(
                dispatcher=dispatcher
            )
        ),
    )

    disable_memory_extraction(
        core
    )

    result = core.chat(
        "Cancella il dato.",
        confirmed=True,
    )

    assert result == "deleted"

    tool_calls = get_tool_calls(
        provider
    )

    assert len(
        tool_calls
    ) == 2

    tool_messages = get_tool_messages(
        tool_calls[1]
    )

    assert tool_messages

    assert any(
        (
            message.get("response")
            == {
                "success": True,
                "output": "deleted",
                "error": None,
            }
        )
        or (
            "deleted"
            in str(message)
        )
        for message in tool_messages
    )
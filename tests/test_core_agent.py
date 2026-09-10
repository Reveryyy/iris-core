from dataclasses import dataclass
from typing import Any

from app.agent import (
    AgentDecision,
    AgentLoop,
    AgentPlan,
    AgentPlanStep,
)
from app.core import IRISCore
from app.tools import (
    EchoTool,
    PermissionManager,
    ToolDispatcher,
    ToolExecutionService,
    ToolRegistry,
)


@dataclass
class FakeMemoryRecord:
    content: str
    importance: int = 1


class FakeMemory:

    def __init__(self):
        self.remembered: list[dict[str, Any]] = []

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
        self.remembered.append(
            {
                "content": content,
                "memory_type": memory_type,
                "importance": importance,
                "confidence": confidence,
                "source": source,
            }
        )

        return None

    def recall(
        self,
        memory_id: int,
    ):
        return None


class FakeRouter:

    def __init__(self):
        self.calls: list[
            dict[str, Any]
        ] = []

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

        return """
        {
            "type": "final",
            "content": "memory ignored",
            "name": null,
            "arguments": {}
        }
        """


class FakePlanner:

    def __init__(
        self,
        plan: AgentPlan,
    ):
        self.plan_result = plan

        self.calls: list[
            dict[str, Any]
        ] = []

    def plan(
        self,
        goal: str,
        context: str | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> AgentPlan:

        self.calls.append(
            {
                "goal": goal,
                "context": context,
                "tool_definitions": tool_definitions,
            }
        )

        return self.plan_result


class FakeVerifier:

    def verify(
        self,
        result,
        success_criteria=None,
    ):
        class Verification:
            verified = True
            reason = "Risultato verificato."

        return Verification()


def create_core(
    plan: AgentPlan,
):

    router = FakeRouter()
    memory = FakeMemory()

    registry = ToolRegistry()

    registry.register(
        EchoTool()
    )

    execution_service = ToolExecutionService(
        dispatcher=ToolDispatcher(
            registry=registry,
            permissions=PermissionManager(),
        )
    )

    planner = FakePlanner(
        plan
    )

    agent_loop = AgentLoop(
        planner=planner,
        execution_service=execution_service,
        verifier=FakeVerifier(),
    )

    core = IRISCore(
        router=router,
        memory=memory,
        agent_loop=agent_loop,
    )

    core.memory_extractor.extract = (
        lambda message: []
    )

    return (
        core,
        memory,
        planner,
    )


def test_core_runs_agent_loop():

    plan = AgentPlan(
        goal="Esegui echo.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "ciao",
                },
                description="Esegui echo.",
            ),
        ),
    )

    core, memory, planner = create_core(
        plan
    )

    result = core.run_agent(
        "Esegui echo."
    )

    assert result.decision == AgentDecision.DONE
    assert result.completed is True

    assert len(
        result.steps
    ) == 1

    assert (
        result.steps[0].tool_result.output
        == "ciao"
    )

    assert (
        planner.calls[0]["goal"]
        == "Esegui echo."
    )

    assert (
        "echo"
        in str(
            planner.calls[0]["tool_definitions"]
        )
    )

    assert any(
        item["memory_type"] == "agent_event"
        for item in memory.remembered
    )


def test_core_agent_rejects_missing_agent_loop():

    core = IRISCore(
        router=FakeRouter(),
        memory=FakeMemory(),
    )

    core.memory_extractor.extract = (
        lambda message: []
    )

    try:
        core.run_agent(
            "Esegui qualcosa."
        )
    except RuntimeError as error:
        assert (
            str(error)
            == "Agent Loop non configurato."
        )
    else:
        raise AssertionError(
            "IRISCore avrebbe dovuto rifiutare "
            "l'esecuzione senza Agent Loop."
        )


def test_core_agent_uses_memory_context():

    class MemoryWithContext(FakeMemory):

        def search_semantic(
            self,
            message: str,
            limit: int = 5,
        ):
            memory = FakeMemoryRecord(
                content="Preferisco usare echo.",
                importance=3,
            )

            return [
                (
                    memory,
                    0.95,
                )
            ]

    router = FakeRouter()
    memory = MemoryWithContext()

    registry = ToolRegistry()

    registry.register(
        EchoTool()
    )

    execution_service = ToolExecutionService(
        dispatcher=ToolDispatcher(
            registry=registry,
            permissions=PermissionManager(),
        )
    )

    plan = AgentPlan(
        goal="Esegui echo.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "ciao",
                },
                description="Esegui echo.",
            ),
        ),
    )

    planner = FakePlanner(
        plan
    )

    agent_loop = AgentLoop(
        planner=planner,
        execution_service=execution_service,
        verifier=FakeVerifier(),
    )

    core = IRISCore(
        router=router,
        memory=memory,
        agent_loop=agent_loop,
    )

    core.memory_extractor.extract = (
        lambda message: []
    )

    core.run_agent(
        "Esegui echo."
    )

    assert len(
        planner.calls
    ) == 1

    assert (
        "Preferisco usare echo."
        in planner.calls[0]["context"]
    )

    assert (
        "0.950"
        in planner.calls[0]["context"]
    )
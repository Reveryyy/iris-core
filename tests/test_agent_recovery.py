from typing import Any

from app.agent import (
    AgentDecision,
    AgentLoop,
    AgentPlan,
    AgentPlanStep,
)
from app.tools import (
    EchoTool,
    PermissionManager,
    ToolDispatcher,
    ToolExecutionService,
    ToolRegistry,
    ToolResult,
)


class SequencePlanner:
    def __init__(self, plans: list[AgentPlan]):
        self.plans = list(plans)
        self.calls: list[dict[str, Any]] = []

    def plan(
        self,
        goal: str,
        context: str | None = None,
        tool_definitions=None,
        observations=None,
    ) -> AgentPlan:
        self.calls.append(
            {
                "goal": goal,
                "context": context,
                "tool_definitions": tool_definitions,
                "observations": observations,
            }
        )

        if not self.plans:
            raise AssertionError("Planner chiamato più volte del previsto.")

        return self.plans.pop(0)


class SequenceVerifier:
    def __init__(self, results: list[bool]):
        self.results = list(results)

    def verify(self, result: ToolResult, success_criteria=None):
        if not self.results:
            raise AssertionError("Verifier chiamato più volte del previsto.")

        verified = self.results.pop(0)

        class Verification:
            def __init__(self, value: bool):
                self.verified = value
                self.reason = (
                    "verificato"
                    if value
                    else "fallimento simulato"
                )

        return Verification(verified)


def create_execution_service() -> ToolExecutionService:
    registry = ToolRegistry()
    registry.register(EchoTool())

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(),
    )

    return ToolExecutionService(dispatcher=dispatcher)


def test_agent_loop_can_execute_more_than_ten_steps_without_replanning():
    steps = tuple(
        AgentPlanStep(
            tool_name="echo",
            arguments={"text": f"step-{index}"},
            description=f"Esegui step {index}.",
        )
        for index in range(1, 16)
    )

    planner = SequencePlanner(
        [
            AgentPlan(
                goal="Esegui quindici azioni.",
                steps=steps,
                decision=AgentDecision.DONE,
            )
        ]
    )

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
    )

    result = loop.run(
        goal="Esegui quindici azioni.",
    )

    assert result.completed is True
    assert result.decision == AgentDecision.DONE
    assert len(result.steps) == 15
    assert len(result.observations) == 15
    assert len(planner.calls) == 1


def test_agent_loop_replans_after_failed_action():
    first_plan = AgentPlan(
        goal="Completa il task.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={"text": "azione-fallita"},
                description="Azione che fallisce.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    recovery_plan = AgentPlan(
        goal="Completa il task.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={"text": "recupero"},
                description="Strategia alternativa.",
            ),
        ),
        decision=AgentDecision.DONE,
    )

    planner = SequencePlanner(
        [first_plan, recovery_plan]
    )

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=SequenceVerifier([False, True]),
    )

    result = loop.run(
        goal="Completa il task.",
    )

    assert result.completed is True
    assert result.decision == AgentDecision.DONE
    assert len(result.steps) == 2
    assert result.steps[0].verification.verified is False
    assert result.steps[1].verification.verified is True
    assert result.steps[1].tool_result.output == "recupero"
    assert len(planner.calls) == 2

    recovery_call = planner.calls[1]
    assert recovery_call["observations"]
    failed_observation = recovery_call["observations"][0]
    assert failed_observation.verified is False
    assert failed_observation.error is None
    assert "STATO ESECUZIONE" in recovery_call["context"]


def test_agent_loop_stops_when_planner_repeats_failed_action():
    plan = AgentPlan(
        goal="Completa il task.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={"text": "azione-fallita"},
                description="Azione che fallisce.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    planner = SequencePlanner([plan, plan])

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=SequenceVerifier([False]),
    )

    result = loop.run(
        goal="Completa il task.",
    )

    assert result.completed is False
    assert result.decision == AgentDecision.ASK_USER
    assert len(result.steps) == 1
    assert len(planner.calls) == 2


def test_agent_loop_returns_pending_plan_when_recovery_requires_confirmation():
    first_plan = AgentPlan(
        goal="Apri un'applicazione.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={"text": "app-not-found"},
                description="Simula il rilevamento di un'app non disponibile.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    pending_plan = AgentPlan(
        goal="Apri un'applicazione.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={"text": "installazione-autorizzata"},
                description="Azione da eseguire dopo la conferma dell'utente.",
            ),
        ),
        decision=AgentDecision.ASK_USER,
        message="L'applicazione non è installata. Vuoi procedere con l'installazione?",
    )

    planner = SequencePlanner([first_plan, pending_plan])

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=SequenceVerifier([False]),
    )

    result = loop.run(
        goal="Apri un'applicazione.",
    )

    assert result.completed is False
    assert result.decision == AgentDecision.ASK_USER
    assert result.message == (
        "L'applicazione non è installata. Vuoi procedere con l'installazione?"
    )
    assert len(result.steps) == 1
    assert result.plan.steps[0].arguments == {
        "text": "installazione-autorizzata"
    }

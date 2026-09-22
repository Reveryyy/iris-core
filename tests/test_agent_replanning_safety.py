from typing import Any

from app.agent import (
    AgentDecision,
    AgentLoop,
    AgentObservation,
    AgentPlan,
    AgentPlanStep,
)
from app.tools import (
    EchoTool,
    PermissionManager,
    ToolDispatcher,
    ToolExecutionService,
    ToolRegistry,
)


class SequencePlanner:
    def __init__(
        self,
        plans: list[AgentPlan],
    ) -> None:
        self.plans = list(
            plans
        )

        self.calls: list[
            dict[str, Any]
        ] = []

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
            raise AssertionError(
                "SequencePlanner ha ricevuto "
                "più chiamate di quelle previste."
            )

        return self.plans.pop(
            0
        )


class AlwaysVerifiedVerifier:
    def verify(
        self,
        result,
        success_criteria=None,
    ):
        class Verification:
            verified = True
            reason = "Risultato verificato."

        return Verification()


def create_execution_service():
    registry = ToolRegistry()

    registry.register(
        EchoTool()
    )

    dispatcher = ToolDispatcher(
        registry=registry,
        permissions=PermissionManager(),
    )

    return ToolExecutionService(
        dispatcher=dispatcher
    )


def test_replan_does_not_repeat_already_completed_step():
    first_plan = AgentPlan(
        goal="Scrivi il testo.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "CIAO",
                },
                description="Esegui il primo step.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    second_plan = AgentPlan(
        goal="Scrivi il testo.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "CIAO",
                },
                description="Ripeti lo stesso step.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    planner = SequencePlanner(
        [
            first_plan,
            second_plan,
        ]
    )

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=AlwaysVerifiedVerifier(),
    )

    result = loop.run(
        goal="Scrivi il testo.",
    )

    assert result.completed is True
    assert result.decision == AgentDecision.DONE

    assert len(
        result.steps
    ) == 1

    assert result.steps[0].tool_call.arguments == {
        "text": "CIAO",
    }

    assert len(
        planner.calls
    ) == 2


def test_replan_removes_completed_step_but_keeps_new_step():
    first_plan = AgentPlan(
        goal="Esegui due azioni.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "PRIMO",
                },
                description="Primo step.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    second_plan = AgentPlan(
        goal="Esegui due azioni.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "PRIMO",
                },
                description="Step già completato.",
            ),
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "SECONDO",
                },
                description="Nuovo step.",
            ),
        ),
        decision=AgentDecision.DONE,
    )

    planner = SequencePlanner(
        [
            first_plan,
            second_plan,
        ]
    )

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=AlwaysVerifiedVerifier(),
    )

    result = loop.run(
        goal="Esegui due azioni.",
    )

    assert result.completed is True

    assert len(
        result.steps
    ) == 2

    assert result.steps[0].tool_call.arguments == {
        "text": "PRIMO",
    }

    assert result.steps[1].tool_call.arguments == {
        "text": "SECONDO",
    }


def test_replan_context_marks_verified_actions_as_completed():
    observation = AgentObservation(
        step_index=1,
        tool_name="echo",
        arguments={
            "text": "CIAO",
        },
        success=True,
        output="CIAO",
        verified=True,
        verification_reason="Risultato verificato.",
    )

    context = AgentLoop._build_replan_context(
        context="Contesto iniziale.",
        observations=[
            observation,
        ],
    )

    assert "Contesto iniziale." in context
    assert "success=True" in context
    assert "verified=True" in context
    assert "NON devono essere ripetute" in context
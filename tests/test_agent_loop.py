from app.agent.planner import AgentPlan, AgentPlanStep, AgentPlanner
from typing import Any

import pytest

from app.agent import (
    AgentDecision,
    AgentLoop,
    AgentObservation,
    AgentPlan,
    AgentStepResult,
    AgentPlanStep,
    AgentVerifier,
)
from app.tools.call import ToolCall
from app.tools import (
    EchoTool,
    PermissionManager,
    ToolDispatcher,
    ToolExecutionService,
    ToolRegistry,
    ToolResult,
)


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

        return self.plan_result


class SequencePlanner:

    def __init__(
        self,
        plans: list[AgentPlan],
    ):
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


class FakeVerifier:

    def __init__(
        self,
        verified: bool,
    ):
        self.verified = verified

        self.calls: list[
            tuple[
                ToolResult,
                str | None,
            ]
        ] = []

    def verify(
        self,
        result: ToolResult,
        success_criteria: str | None = None,
    ):

        self.calls.append(
            (
                result,
                success_criteria,
            )
        )

        class Verification:

            def __init__(
                self,
                verified: bool,
            ):
                self.verified = verified
                self.reason = (
                    "fake verification"
                    if verified
                    else "fake verification failed"
                )

        return Verification(
            self.verified
        )


class SequenceVerifier:

    def __init__(
        self,
        results: list[bool],
    ):
        self.results = list(
            results
        )

        self.calls: list[
            tuple[
                ToolResult,
                str | None,
            ]
        ] = []

    def verify(
        self,
        result: ToolResult,
        success_criteria: str | None = None,
    ):

        self.calls.append(
            (
                result,
                success_criteria,
            )
        )

        if not self.results:
            raise AssertionError(
                "SequenceVerifier ha ricevuto "
                "più chiamate di quelle previste."
            )

        verified = self.results.pop(
            0
        )

        class Verification:

            def __init__(
                self,
                verified: bool,
            ):
                self.verified = verified
                self.reason = (
                    "Risultato verificato."
                    if verified
                    else "Risultato non verificato."
                )

        return Verification(
            verified
        )


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


def test_agent_loop_plans_executes_and_verifies():

    plan = AgentPlan(
        goal="Esegui echo.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "ciao",
                },
                description="Restituisce ciao.",
                success_criteria="Il risultato deve essere ciao.",
            ),
        ),
        decision=AgentDecision.DONE,
    )

    planner = FakePlanner(
        plan
    )

    verifier = FakeVerifier(
        verified=True
    )

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=verifier,
    )

    result = loop.run(
        goal="Esegui echo.",
        context="test",
    )

    assert result.completed is True
    assert result.decision == AgentDecision.DONE
    assert result.goal == "Esegui echo."

    assert len(
        result.steps
    ) == 1

    step = result.steps[0]

    assert step.tool_call.name == "echo"
    assert step.tool_call.arguments == {
        "text": "ciao",
    }

    assert step.tool_result.success is True
    assert step.tool_result.output == "ciao"

    assert step.verification.verified is True

    assert step.observation.tool_name == "echo"
    assert step.observation.success is True
    assert step.observation.verified is True
    assert step.observation.output == "ciao"

    assert len(
        result.observations
    ) == 1

    assert len(
        planner.calls
    ) == 1


def test_agent_loop_continues_after_verified_step():

    first_plan = AgentPlan(
        goal="Esegui due azioni.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "primo",
                },
                description="Primo step.",
                success_criteria="Il primo step deve riuscire.",
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
                    "text": "secondo",
                },
                description="Secondo step.",
                success_criteria="Il secondo step deve riuscire.",
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

    verifier = SequenceVerifier(
        [
            True,
            True,
        ]
    )

    loop = AgentLoop(
        planner=planner,
        execution_service=create_execution_service(),
        verifier=verifier,
    )

    result = loop.run(
        goal="Esegui due azioni.",
        context="contesto iniziale",
    )

    assert result.completed is True
    assert result.decision == AgentDecision.DONE

    assert len(
        result.steps
    ) == 2

    first_step = result.steps[0]
    second_step = result.steps[1]

    assert first_step.tool_call.arguments == {
        "text": "primo",
    }

    assert first_step.tool_result.output == "primo"
    assert first_step.verification.verified is True

    assert second_step.tool_call.arguments == {
        "text": "secondo",
    }

    assert second_step.tool_result.output == "secondo"
    assert second_step.verification.verified is True

    assert len(
        result.observations
    ) == 2

    assert len(
        planner.calls
    ) == 2

    replan_call = planner.calls[1]

    assert replan_call["observations"]

    observation = replan_call[
        "observations"
    ][0]

    assert isinstance(
        observation,
        AgentObservation,
    )

    assert observation.tool_name == "echo"
    assert observation.output == "primo"
    assert observation.verified is True

    assert "primo" in replan_call["context"]


def test_agent_loop_does_not_continue_after_failed_verification():

    plan = AgentPlan(
        goal="Esegui due azioni.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "primo",
                },
                description="Primo step.",
            ),
        ),
        decision=AgentDecision.CONTINUE,
    )

    loop = AgentLoop(
        planner=FakePlanner(plan),
        execution_service=create_execution_service(),
        verifier=FakeVerifier(
            verified=False
        ),
    )

    result = loop.run(
        goal="Esegui due azioni.",
    )

    assert result.completed is False
    assert result.decision == AgentDecision.ASK_USER

    assert len(
        result.steps
    ) == 1

    assert len(
        result.observations
    ) == 1

    assert (
        result.observations[0].verified
        is False
    )


def test_agent_loop_final_message_prefers_tool_user_message_over_planner_message():
    plan = AgentPlan(
        goal="Apri un'applicazione.",
        steps=(
            AgentPlanStep(
                tool_name="open_application",
                arguments={"name": "Calcolatrice"},
                description="Apri la Calcolatrice.",
            ),
        ),
        decision=AgentDecision.DONE,
        message="Piano generato per aprire la calcolatrice.",
    )

    step = AgentStepResult(
        step=plan.steps[0],
        tool_call=ToolCall(
            name="open_application",
            arguments={"name": "Calcolatrice"},
            call_id="test",
        ),
        tool_result=ToolResult(
            success=True,
            output={
                "application": "Calcolatrice",
                "already_running": True,
                "user_message": "Calcolatrice è già in esecuzione.",
            },
        ),
        verification=AgentVerifier().verify(
            ToolResult(
                success=True,
                output={
                    "application": "Calcolatrice",
                    "already_running": True,
                    "user_message": "Calcolatrice è già in esecuzione.",
                },
            )
        ),
        observation=AgentObservation(
            step_index=1,
            tool_name="open_application",
            arguments={"name": "Calcolatrice"},
            success=True,
            output={
                "application": "Calcolatrice",
                "already_running": True,
                "user_message": "Calcolatrice è già in esecuzione.",
            },
            verified=True,
        ),
    )

    loop = AgentLoop.__new__(AgentLoop)

    message = loop._build_final_message(
        goal=plan.goal,
        plan=plan,
        steps=[step],
    )

    assert message == "Calcolatrice è già in esecuzione."


def test_agent_loop_ask_user_decision():

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
        decision=AgentDecision.ASK_USER,
        message="Serve una scelta dell'utente.",
    )

    loop = AgentLoop(
        planner=FakePlanner(plan),
        execution_service=create_execution_service(),
        verifier=FakeVerifier(
            verified=True
        ),
    )

    result = loop.run(
        goal="Esegui echo.",
    )

    assert result.completed is False
    assert result.decision == AgentDecision.ASK_USER

    assert (
        result.message
        == "Serve una scelta dell'utente."
    )

    assert len(
        result.steps
    ) == 1


def test_agent_loop_does_not_execute_unknown_tool():

    plan = AgentPlan(
        goal="Esegui un tool inesistente.",
        steps=(
            AgentPlanStep(
                tool_name="does_not_exist",
                arguments={},
                description="Tool inesistente.",
            ),
        ),
        decision=AgentDecision.DONE,
    )

    loop = AgentLoop(
        planner=FakePlanner(plan),
        execution_service=create_execution_service(),
    )

    result = loop.run(
        goal="Esegui un tool inesistente.",
    )

    assert result.completed is False
    assert result.decision == AgentDecision.ASK_USER

    assert len(
        result.steps
    ) == 1

    step = result.steps[0]

    assert step.tool_result.success is False

    assert (
        "Tool non trovato"
        in step.tool_result.error
    )

    assert step.verification.verified is False


def test_agent_loop_respects_max_steps():

    first_plan = AgentPlan(
        goal="Esegui due azioni.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "uno",
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
                    "text": "due",
                },
                description="Secondo step.",
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
        verifier=FakeVerifier(
            verified=True
        ),
        max_steps=1,
    )

    result = loop.run(
        goal="Esegui due azioni.",
    )

    assert result.completed is False
    assert result.decision == AgentDecision.CONTINUE
    assert len(result.steps) == 1

    assert len(
        planner.calls
    ) == 1


def test_agent_loop_requires_positive_max_steps():

    plan = AgentPlan(
        goal="Test.",
        steps=(
            AgentPlanStep(
                tool_name="echo",
                arguments={
                    "text": "test",
                },
                description="Test.",
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="max_steps",
    ):
        AgentLoop(
            planner=FakePlanner(plan),
            execution_service=create_execution_service(),
            max_steps=0,
        )


def test_agent_plan_rejects_empty_steps():

    with pytest.raises(
        ValueError,
        match="almeno uno step",
    ):
        AgentPlan(
            goal="Test.",
            steps=(),
        )


def test_agent_plan_step_rejects_empty_tool_name():

    with pytest.raises(
        ValueError,
        match="non può essere vuoto",
    ):
        AgentPlanStep(
            tool_name="",
            arguments={},
            description="Test.",
        )


def test_agent_observation_serializes_execution_state():

    observation = AgentObservation(
        step_index=1,
        tool_name="echo",
        arguments={
            "text": "ciao",
        },
        success=True,
        output="ciao",
        verified=True,
        verification_reason="Risultato verificato.",
    )

    data = observation.to_dict()

    assert data["step_index"] == 1
    assert data["tool_name"] == "echo"
    assert data["arguments"] == {
        "text": "ciao",
    }
    assert data["success"] is True
    assert data["output"] == "ciao"
    assert data["verified"] is True

    context = observation.to_context()

    assert "echo" in context
    assert "ciao" in context
    assert "Verificato: True" in context


def test_agent_verifier_accepts_successful_result():

    verifier = AgentVerifier()

    result = verifier.verify(
        ToolResult(
            success=True,
            output="ok",
        ),
        success_criteria="Deve restituire ok.",
    )

    assert result.verified is True

    assert (
        "success=true"
        in result.reason
    )


def test_agent_verifier_rejects_failed_result():

    verifier = AgentVerifier()

    result = verifier.verify(
        ToolResult(
            success=False,
            error="boom",
        )
    )

    assert result.verified is False
    assert "boom" in result.reason


def test_agent_planner_rejects_invalid_goal():

    class DummyRouter:

        def generate(
            self,
            *args,
            **kwargs,
        ):
            return "{}"

    planner = AgentPlanner(
        router=DummyRouter()
    )

    with pytest.raises(
        ValueError,
        match="non può essere vuoto",
    ):
        planner.plan(
            ""
        )
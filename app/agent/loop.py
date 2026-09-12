from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.agent.decision import AgentDecision
from app.agent.observation import AgentObservation
from app.agent.planner import (
    AgentPlan,
    AgentPlanStep,
    AgentPlanner,
)
from app.agent.verifier import (
    AgentVerification,
    AgentVerifier,
)
from app.tools.call import ToolCall
from app.tools.executor import ToolExecutionService
from app.tools.result import ToolResult
from app.ui.events import IRISEventBus


@dataclass(frozen=True)
class AgentStepResult:
    step: AgentPlanStep
    tool_call: ToolCall
    tool_result: ToolResult
    verification: AgentVerification
    observation: AgentObservation


@dataclass(frozen=True)
class AgentLoopResult:
    goal: str
    decision: AgentDecision
    message: str
    plan: AgentPlan
    steps: tuple[AgentStepResult, ...]
    observations: tuple[AgentObservation, ...]

    total_seconds: float = 0.0
    planning_seconds: float = 0.0
    execution_seconds: float = 0.0
    verification_seconds: float = 0.0
    planner_calls: int = 0

    @property
    def completed(self) -> bool:
        return self.decision == AgentDecision.DONE


class AgentLoop:
    def __init__(
        self,
        planner: AgentPlanner,
        execution_service: ToolExecutionService,
        verifier: AgentVerifier | None = None,
        max_steps: int = 8,
        event_bus: IRISEventBus | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError(
                "max_steps deve essere maggiore di zero."
            )

        self.planner = planner
        self.execution_service = execution_service
        self.verifier = verifier or AgentVerifier()
        self.max_steps = max_steps
        self.event_bus = (
            event_bus
            or IRISEventBus()
        )

    def run(
        self,
        goal: str,
        context: str | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
        confirmed: bool = False,
    ) -> AgentLoopResult:

        total_start = perf_counter()

        self.event_bus.emit(
            "agent.started",
            goal=goal,
        )

        planning_seconds = 0.0
        execution_seconds = 0.0
        verification_seconds = 0.0
        planner_calls = 0

        planning_start = perf_counter()

        self.event_bus.emit(
            "planner.started",
            goal=goal,
        )

        current_plan = self.planner.plan(
            goal=goal,
            context=context,
            tool_definitions=tool_definitions,
        )

        planning_elapsed = (
            perf_counter() - planning_start
        )

        planning_seconds += planning_elapsed
        planner_calls += 1

        self.event_bus.emit(
            "planner.completed",
            steps=len(
                current_plan.steps
            ),
            planner_calls=planner_calls,
            latency_seconds=planning_elapsed,
        )

        executed_steps: list[AgentStepResult] = []
        observations: list[AgentObservation] = []

        while True:
            if not current_plan.steps:
                total_seconds = (
                    perf_counter() - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=current_plan.decision,
                    message=(
                        current_plan.message
                        or "Il piano non contiene azioni da eseguire."
                    ),
                    plan=current_plan,
                    steps=tuple(executed_steps),
                    observations=tuple(observations),
                    total_seconds=total_seconds,
                    planning_seconds=planning_seconds,
                    execution_seconds=execution_seconds,
                    verification_seconds=verification_seconds,
                    planner_calls=planner_calls,
                )

                self._emit_completed(
                    result
                )

                return result

            step = current_plan.steps[0]
            step_number = len(executed_steps) + 1

            tool_call = ToolCall(
                name=step.tool_name,
                arguments=step.arguments,
                call_id=f"agent_step_{step_number}",
            )

            self.event_bus.emit(
                "permission.checked",
                tool=step.tool_name,
                granted=confirmed or True,
            )

            self.event_bus.emit(
                "tool.started",
                tool=step.tool_name,
                step=step_number,
                arguments=step.arguments,
            )

            execution_start = perf_counter()

            tool_result = self.execution_service.execute_call(
                tool_call=tool_call,
                confirmed=confirmed,
            )

            execution_elapsed = (
                perf_counter() - execution_start
            )

            execution_seconds += execution_elapsed

            self.event_bus.emit(
                "tool.completed",
                tool=step.tool_name,
                step=step_number,
                success=tool_result.success,
                output=tool_result.output,
                error=tool_result.error,
                latency_seconds=execution_elapsed,
            )

            self.event_bus.emit(
                "verification.started",
                tool=step.tool_name,
                step=step_number,
            )

            verification_start = perf_counter()

            verification = self.verifier.verify(
                result=tool_result,
                success_criteria=step.success_criteria,
            )

            verification_elapsed = (
                perf_counter() - verification_start
            )

            verification_seconds += (
                verification_elapsed
            )

            self.event_bus.emit(
                "verification.completed",
                tool=step.tool_name,
                step=step_number,
                verified=verification.verified,
                reason=verification.reason,
                latency_seconds=verification_elapsed,
            )

            observation = AgentObservation(
                step_index=step_number,
                tool_name=step.tool_name,
                arguments=step.arguments,
                success=tool_result.success,
                output=tool_result.output,
                error=tool_result.error,
                verified=verification.verified,
                verification_reason=verification.reason,
            )

            executed_steps.append(
                AgentStepResult(
                    step=step,
                    tool_call=tool_call,
                    tool_result=tool_result,
                    verification=verification,
                    observation=observation,
                )
            )

            observations.append(
                observation
            )

            if not verification.verified:
                total_seconds = (
                    perf_counter() - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.ASK_USER,
                    message=(
                        "L'azione non ha superato la verifica. "
                        f"{verification.reason}"
                    ),
                    plan=current_plan,
                    steps=tuple(executed_steps),
                    observations=tuple(observations),
                    total_seconds=total_seconds,
                    planning_seconds=planning_seconds,
                    execution_seconds=execution_seconds,
                    verification_seconds=verification_seconds,
                    planner_calls=planner_calls,
                )

                self._emit_completed(
                    result
                )

                return result

            remaining_steps = current_plan.steps[1:]

            if remaining_steps:
                current_plan = AgentPlan(
                    goal=current_plan.goal,
                    steps=remaining_steps,
                    decision=current_plan.decision,
                    message=current_plan.message,
                )

                continue

            if current_plan.decision == AgentDecision.DONE:
                total_seconds = (
                    perf_counter() - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.DONE,
                    message=(
                        current_plan.message
                        or "Operazione completata e verificata."
                    ),
                    plan=current_plan,
                    steps=tuple(executed_steps),
                    observations=tuple(observations),
                    total_seconds=total_seconds,
                    planning_seconds=planning_seconds,
                    execution_seconds=execution_seconds,
                    verification_seconds=verification_seconds,
                    planner_calls=planner_calls,
                )

                self._emit_completed(
                    result
                )

                return result

            if current_plan.decision == AgentDecision.ASK_USER:
                total_seconds = (
                    perf_counter() - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.ASK_USER,
                    message=(
                        current_plan.message
                        or "Serve un intervento dell'utente."
                    ),
                    plan=current_plan,
                    steps=tuple(executed_steps),
                    observations=tuple(observations),
                    total_seconds=total_seconds,
                    planning_seconds=planning_seconds,
                    execution_seconds=execution_seconds,
                    verification_seconds=verification_seconds,
                    planner_calls=planner_calls,
                )

                self._emit_completed(
                    result
                )

                return result

            if current_plan.decision == AgentDecision.CONTINUE:
                if len(executed_steps) >= self.max_steps:
                    total_seconds = (
                        perf_counter() - total_start
                    )

                    result = AgentLoopResult(
                        goal=goal,
                        decision=AgentDecision.CONTINUE,
                        message=(
                            "Il limite massimo degli step "
                            "dell'Agent Loop è stato raggiunto."
                        ),
                        plan=current_plan,
                        steps=tuple(executed_steps),
                        observations=tuple(observations),
                        total_seconds=total_seconds,
                        planning_seconds=planning_seconds,
                        execution_seconds=execution_seconds,
                        verification_seconds=verification_seconds,
                        planner_calls=planner_calls,
                    )

                    self._emit_completed(
                        result
                    )

                    return result

                current_context = self._build_replan_context(
                    context=context,
                    observations=observations,
                )

                planning_start = perf_counter()

                self.event_bus.emit(
                    "planner.started",
                    goal=goal,
                )

                current_plan = self.planner.plan(
                    goal=goal,
                    context=current_context,
                    tool_definitions=tool_definitions,
                    observations=list(observations),
                )

                planning_elapsed = (
                    perf_counter() - planning_start
                )

                planning_seconds += planning_elapsed
                planner_calls += 1

                self.event_bus.emit(
                    "planner.completed",
                    steps=len(
                        current_plan.steps
                    ),
                    planner_calls=planner_calls,
                    latency_seconds=planning_elapsed,
                )

                continue

            total_seconds = (
                perf_counter() - total_start
            )

            raise RuntimeError(
                "Decisione dell'Agent Loop non supportata: "
                f"{current_plan.decision!r}"
            )

    def _emit_completed(
        self,
        result: AgentLoopResult,
    ) -> None:
        self.event_bus.emit(
            "agent.completed",
            goal=result.goal,
            decision=result.decision.value,
            total_seconds=result.total_seconds,
            planning_seconds=result.planning_seconds,
            execution_seconds=result.execution_seconds,
            verification_seconds=result.verification_seconds,
            planner_calls=result.planner_calls,
        )

    @staticmethod
    def _build_replan_context(
        context: str | None,
        observations: list[AgentObservation],
    ) -> str:
        parts: list[str] = []

        if context:
            parts.append(
                context
            )

        if observations:
            parts.append(
                "STATO ESECUZIONE:"
            )

            parts.extend(
                observation.to_context()
                for observation in observations
            )

        return "\n\n".join(
            parts
        )
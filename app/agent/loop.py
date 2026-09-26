from __future__ import annotations

import json
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
        max_steps: int = 64,
        max_recovery_attempts: int = 3,
        event_bus: IRISEventBus | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError(
                "max_steps deve essere maggiore di zero."
            )

        if max_recovery_attempts < 0:
            raise ValueError(
                "max_recovery_attempts non può essere negativo."
            )

        self.planner = planner
        self.execution_service = execution_service
        self.verifier = verifier or AgentVerifier()
        self.max_steps = max_steps
        self.max_recovery_attempts = max_recovery_attempts
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
            perf_counter()
            - planning_start
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

        executed_steps: list[
            AgentStepResult
        ] = []

        observations: list[
            AgentObservation
        ] = []

        while True:
            if not current_plan.steps:
                total_seconds = (
                    perf_counter()
                    - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=current_plan.decision,
                    message=self._build_final_message(
                        goal=goal,
                        plan=current_plan,
                        steps=executed_steps,
                    ),
                    plan=current_plan,
                    steps=tuple(
                        executed_steps
                    ),
                    observations=tuple(
                        observations
                    ),
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
            step_number = (
                len(executed_steps)
                + 1
            )

            tool_call = ToolCall(
                name=step.tool_name,
                arguments=step.arguments,
                call_id=(
                    f"agent_step_{step_number}"
                ),
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

            tool_result = (
                self.execution_service.execute_call(
                    tool_call=tool_call,
                    confirmed=confirmed,
                )
            )

            execution_elapsed = (
                perf_counter()
                - execution_start
            )

            execution_seconds += (
                execution_elapsed
            )

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

            verification_start = (
                perf_counter()
            )

            verification = self.verifier.verify(
                result=tool_result,
                success_criteria=step.success_criteria,
            )

            verification_elapsed = (
                perf_counter()
                - verification_start
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
                recovery_result = self._recover_after_failure(
                    goal=goal,
                    context=context,
                    tool_definitions=tool_definitions,
                    observations=observations,
                    failed_step=step,
                    recovery_attempts=sum(
                        1
                        for observation in observations
                        if not observation.verified
                    ),
                    planning_seconds=planning_seconds,
                    planner_calls=planner_calls,
                    total_start=total_start,
                    executed_steps=executed_steps,
                )

                if recovery_result is not None:
                    result, recovered_plan, planning_delta, planner_delta = recovery_result
                    planning_seconds += planning_delta
                    planner_calls += planner_delta

                    if result is not None:
                        self._emit_completed(result)
                        return result

                    if recovered_plan is not None:
                        current_plan = recovered_plan
                        continue

                total_seconds = (
                    perf_counter()
                    - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.ASK_USER,
                    message=(
                        "L'azione non ha superato la verifica. "
                        f"{verification.reason}"
                    ),
                    plan=current_plan,
                    steps=tuple(
                        executed_steps
                    ),
                    observations=tuple(
                        observations
                    ),
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

            remaining_steps = (
                current_plan.steps[1:]
            )

            if remaining_steps:
                current_plan = AgentPlan(
                    goal=current_plan.goal,
                    steps=remaining_steps,
                    decision=current_plan.decision,
                    message=current_plan.message,
                )

                continue

            if (
                current_plan.decision
                == AgentDecision.DONE
            ):
                total_seconds = (
                    perf_counter()
                    - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.DONE,
                    message=self._build_final_message(
                        goal=goal,
                        plan=current_plan,
                        steps=executed_steps,
                    ),
                    plan=current_plan,
                    steps=tuple(
                        executed_steps
                    ),
                    observations=tuple(
                        observations
                    ),
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

            if (
                current_plan.decision
                == AgentDecision.ASK_USER
            ):
                total_seconds = (
                    perf_counter()
                    - total_start
                )

                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.ASK_USER,
                    message=(
                        current_plan.message
                        or "Serve un intervento dell'utente."
                    ),
                    plan=current_plan,
                    steps=tuple(
                        executed_steps
                    ),
                    observations=tuple(
                        observations
                    ),
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

            if (
                current_plan.decision
                == AgentDecision.CONTINUE
            ):
                if len(executed_steps) >= (
                    self.max_steps
                ):
                    total_seconds = (
                        perf_counter()
                        - total_start
                    )

                    result = AgentLoopResult(
                        goal=goal,
                        decision=AgentDecision.CONTINUE,
                        message=(
                            "Il limite massimo degli step "
                            "dell'Agent Loop è stato raggiunto."
                        ),
                        plan=current_plan,
                        steps=tuple(
                            executed_steps
                        ),
                        observations=tuple(
                            observations
                        ),
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

                current_context = (
                    self._build_replan_context(
                        context=context,
                        observations=observations,
                    )
                )

                planning_start = perf_counter()

                self.event_bus.emit(
                    "planner.started",
                    goal=goal,
                )

                replanned_plan = (
                    self.planner.plan(
                        goal=goal,
                        context=current_context,
                        tool_definitions=tool_definitions,
                        observations=list(
                            observations
                        ),
                    )
                )

                planning_elapsed = (
                    perf_counter()
                    - planning_start
                )

                planning_seconds += (
                    planning_elapsed
                )

                planner_calls += 1

                self.event_bus.emit(
                    "planner.completed",
                    steps=len(
                        replanned_plan.steps
                    ),
                    planner_calls=planner_calls,
                    latency_seconds=planning_elapsed,
                )

                sanitized_plan = (
                    self._remove_replayed_steps(
                        plan=replanned_plan,
                        observations=observations,
                        goal=goal,
                    )
                )

                if sanitized_plan is None:
                    total_seconds = (
                        perf_counter()
                        - total_start
                    )

                    if (
                        replanned_plan.decision
                        == AgentDecision.DONE
                    ):
                        decision = AgentDecision.DONE
                        message = self._build_final_message(
                            goal=goal,
                            plan=replanned_plan,
                            steps=executed_steps,
                        )
                    else:
                        # Un replan CONTINUE composto soltanto da azioni già
                        # eseguite non dimostra il completamento dell'obiettivo.
                        # Non trasformiamo mai una pianificazione incompleta
                        # in un falso DONE.
                        decision = AgentDecision.ASK_USER
                        message = (
                            replanned_plan.message
                            or (
                                "Il Planner non ha prodotto una nuova azione "
                                "eseguibile dopo le operazioni già completate."
                            )
                        )

                    result = AgentLoopResult(
                        goal=goal,
                        decision=decision,
                        message=message,
                        plan=replanned_plan,
                        steps=tuple(
                            executed_steps
                        ),
                        observations=tuple(
                            observations
                        ),
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

                current_plan = sanitized_plan

                continue

            total_seconds = (
                perf_counter()
                - total_start
            )

            raise RuntimeError(
                "Decisione dell'Agent Loop non supportata: "
                f"{current_plan.decision!r}"
            )

    def _recover_after_failure(
        self,
        goal: str,
        context: str | None,
        tool_definitions: list[dict[str, Any]] | None,
        observations: list[AgentObservation],
        failed_step: AgentPlanStep,
        recovery_attempts: int,
        planning_seconds: float,
        planner_calls: int,
        total_start: float,
        executed_steps: list[AgentStepResult],
    ) -> tuple[AgentLoopResult | None, AgentPlan | None, float, int] | None:
        """Replanifica dopo un fallimento invece di abbandonare subito il goal."""
        if recovery_attempts > self.max_recovery_attempts:
            return None

        current_context = self._build_replan_context(
            context=context,
            observations=observations,
        )

        planning_start = perf_counter()

        self.event_bus.emit(
            "planner.started",
            goal=goal,
            recovery=True,
            failed_tool=failed_step.tool_name,
        )

        replanned_plan = self.planner.plan(
            goal=goal,
            context=current_context,
            tool_definitions=tool_definitions,
            observations=list(observations),
        )

        planning_elapsed = perf_counter() - planning_start

        self.event_bus.emit(
            "planner.completed",
            steps=len(replanned_plan.steps),
            planner_calls=planner_calls + 1,
            recovery=True,
            latency_seconds=planning_elapsed,
        )

        if replanned_plan.decision == AgentDecision.ASK_USER:
            result = AgentLoopResult(
                goal=goal,
                decision=AgentDecision.ASK_USER,
                message=(
                    replanned_plan.message
                    or (
                        "L'azione precedente è fallita e serve una decisione "
                        "dell'utente prima di continuare."
                    )
                ),
                plan=replanned_plan,
                steps=tuple(executed_steps),
                observations=tuple(observations),
                total_seconds=perf_counter() - total_start,
                planning_seconds=planning_seconds + planning_elapsed,
                execution_seconds=0.0,
                verification_seconds=0.0,
                planner_calls=planner_calls + 1,
            )
            return result, None, planning_elapsed, 1

        failed_signature = self._step_signature(
            tool_name=failed_step.tool_name,
            arguments=failed_step.arguments,
        )

        first_new_step = (
            replanned_plan.steps[0]
            if replanned_plan.steps
            else None
        )

        if first_new_step is not None:
            first_signature = self._step_signature(
                tool_name=first_new_step.tool_name,
                arguments=first_new_step.arguments,
            )
        else:
            first_signature = None

        if first_signature == failed_signature:
            result = AgentLoopResult(
                goal=goal,
                decision=AgentDecision.ASK_USER,
                message=(
                    replanned_plan.message
                    or (
                        "Il Planner ha riproposto l'azione che ha appena "
                        "fallito. Serve un intervento dell'utente o una "
                        "strategia alternativa."
                    )
                ),
                plan=replanned_plan,
                steps=tuple(executed_steps),
                observations=tuple(observations),
                total_seconds=perf_counter() - total_start,
                planning_seconds=planning_seconds + planning_elapsed,
                execution_seconds=0.0,
                verification_seconds=0.0,
                planner_calls=planner_calls + 1,
            )
            return result, None, planning_elapsed, 1

        sanitized_plan = self._remove_replayed_steps(
            plan=replanned_plan,
            observations=observations,
            goal=goal,
        )

        if sanitized_plan is None:
            if replanned_plan.decision == AgentDecision.DONE:
                result = AgentLoopResult(
                    goal=goal,
                    decision=AgentDecision.DONE,
                    message=self._build_final_message(
                        goal=goal,
                        plan=replanned_plan,
                        steps=executed_steps,
                    ),
                    plan=replanned_plan,
                    steps=tuple(executed_steps),
                    observations=tuple(observations),
                    total_seconds=perf_counter() - total_start,
                    planning_seconds=planning_seconds + planning_elapsed,
                    execution_seconds=0.0,
                    verification_seconds=0.0,
                    planner_calls=planner_calls + 1,
                )
                return result, None, planning_elapsed, 1

            result = AgentLoopResult(
                goal=goal,
                decision=AgentDecision.ASK_USER,
                message=(
                    replanned_plan.message
                    or "Il Planner non ha prodotto una strategia di recupero eseguibile."
                ),
                plan=replanned_plan,
                steps=tuple(executed_steps),
                observations=tuple(observations),
                total_seconds=perf_counter() - total_start,
                planning_seconds=planning_seconds + planning_elapsed,
                execution_seconds=0.0,
                verification_seconds=0.0,
                planner_calls=planner_calls + 1,
            )
            return result, None, planning_elapsed, 1

        return None, sanitized_plan, planning_elapsed, 1

    def _remove_replayed_steps(
        self,
        plan: AgentPlan,
        observations: list[AgentObservation],
        goal: str,
    ) -> AgentPlan | None:
        """
        Rimuove dal replan le azioni già eseguite e verificate.

        Questa protezione è applicata esclusivamente ai replanning:
        non impedisce a un piano iniziale di contenere intenzionalmente
        la stessa azione più volte.

        Restituisce None quando il nuovo piano è composto soltanto
        da azioni già completate. In quel caso l'Agent Loop può
        considerare il goal completato senza rieseguire nulla.

        Una ripetizione esplicita richiesta dall'utente non viene
        filtrata.
        """

        if not observations:
            return plan

        if self._goal_explicitly_requests_repetition(
            goal
        ):
            return plan

        completed_signatures = {
            self._step_signature(
                tool_name=observation.tool_name,
                arguments=observation.arguments,
            )
            for observation in observations
            if (
                observation.success
                and observation.verified
            )
        }

        if not completed_signatures:
            return plan

        remaining_steps: list[
            AgentPlanStep
        ] = []

        removed_any = False

        for step in plan.steps:
            signature = (
                self._step_signature(
                    tool_name=step.tool_name,
                    arguments=step.arguments,
                )
            )

            if signature in completed_signatures:
                removed_any = True
                continue

            remaining_steps.append(
                step
            )

        if not removed_any:
            return plan

        if not remaining_steps:
            return None

        return AgentPlan(
            goal=plan.goal,
            steps=tuple(
                remaining_steps
            ),
            decision=plan.decision,
            message=plan.message,
        )

    @staticmethod
    def _step_signature(
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        try:
            return json.dumps(
                {
                    "tool_name": tool_name,
                    "arguments": arguments,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(
                    ",",
                    ":",
                ),
            )
        except (
            TypeError,
            ValueError,
        ):
            return repr(
                (
                    tool_name,
                    arguments,
                )
            )

    @staticmethod
    def _goal_explicitly_requests_repetition(
        goal: str,
    ) -> bool:
        normalized = (
            goal.strip()
            .lower()
        )

        repetition_markers = (
            "ripeti",
            "di nuovo",
            "ancora",
            "due volte",
            "2 volte",
            "tre volte",
            "3 volte",
            "ripetilo",
            "ripetila",
            "ripeterlo",
            "ripeterla",
        )

        return any(
            marker in normalized
            for marker in repetition_markers
        )

    def _build_final_message(
        self,
        goal: str,
        plan: AgentPlan,
        steps: list[AgentStepResult],
    ) -> str:
        """
        Determina il messaggio finale destinato all'utente.

        Priorità:
        1. user_message prodotto dal tool.
        2. message prodotto dal Planner.
        3. altri campi testuali utili del risultato.
        4. fallback generico.
        """

        for step_result in reversed(
            steps
        ):
            if not step_result.tool_result.success:
                continue

            output = (
                step_result.tool_result.output
            )

            detailed_message = (
                self._format_tool_output_for_user(
                    output
                )
            )

            if detailed_message:
                return detailed_message

        if plan.message:
            return plan.message

        for step_result in reversed(
            steps
        ):
            if not step_result.tool_result.success:
                continue

            output = (
                step_result.tool_result.output
            )

            if isinstance(
                output,
                dict,
            ):
                user_message = output.get(
                    "user_message"
                )

                if (
                    isinstance(
                        user_message,
                        str,
                    )
                    and user_message.strip()
                ):
                    return user_message.strip()

                for key in (
                    "message",
                    "response",
                    "answer",
                    "text",
                ):
                    value = output.get(
                        key
                    )

                    if (
                        isinstance(
                            value,
                            str,
                        )
                        and value.strip()
                    ):
                        return value.strip()

        return (
            "Operazione completata e verificata."
        )

    @staticmethod
    def _format_tool_output_for_user(
        output: Any,
    ) -> str | None:
        """
        Trasforma i risultati informativi dei tool in un output realmente
        leggibile dall'utente.

        I tool che restituiscono solo un user_message continuano a usare
        quello. Quando invece sono presenti dati richiesti dall'utente
        (contenuto file, elenco directory, risultati di ricerca o stdout),
        quei dati hanno la precedenza sul messaggio generico.
        """
        if isinstance(
            output,
            str,
        ):
            return output if output.strip() else None

        if not isinstance(
            output,
            dict,
        ):
            return None

        content = output.get(
            "content"
        )

        if isinstance(
            content,
            str,
        ):
            path = output.get(
                "path"
            )

            header = (
                f"Contenuto di '{path}':"
                if path
                else "Contenuto:"
            )

            return (
                header
                + "\n\n"
                + content
            )

        entries = output.get(
            "entries"
        )

        if isinstance(
            entries,
            list,
        ):
            path = output.get(
                "path"
            )

            title = (
                f"Contenuto di '{path}':"
                if path
                else "Contenuto della directory:"
            )

            return (
                title
                + "\n"
                + json.dumps(
                    entries,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        results = output.get(
            "results"
        )

        if isinstance(
            results,
            list,
        ):
            title = "Risultati della ricerca:"
            return (
                title
                + "\n"
                + json.dumps(
                    results,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        stdout = output.get(
            "stdout"
        )

        stderr = output.get(
            "stderr"
        )

        if (
            isinstance(stdout, str)
            or isinstance(stderr, str)
        ):
            parts: list[str] = []

            if isinstance(
                stdout,
                str,
            ) and stdout:
                parts.append(
                    "STDOUT:\n"
                    + stdout
                )

            if isinstance(
                stderr,
                str,
            ) and stderr:
                parts.append(
                    "STDERR:\n"
                    + stderr
                )

            if parts:
                return "\n\n".join(
                    parts
                )

        return None

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

            parts.append(
                "Le azioni sotto riportate sono già state "
                "eseguite. Quelle con success=True e verified=True "
                "sono già completate e NON devono essere ripetute "
                "nel nuovo piano, salvo richiesta esplicita "
                "dell'utente di ripeterle."
            )

            parts.extend(
                observation.to_context()
                for observation in observations
            )

        return "\n\n".join(
            parts
        )


__all__ = [
    "AgentStepResult",
    "AgentLoopResult",
    "AgentLoop",
]
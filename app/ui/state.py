from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from app.ui.events import IRISEvent


@dataclass
class TerminalState:
    online: bool = True

    provider: str = "-"
    model: str = "-"
    mode: str = "AUTO"
    task: str = "general"

    phase: str = "idle"
    activity: str = "In attesa..."
    detail: str = ""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    context_tokens: int | None = None
    context_limit: int | None = None

    tool_name: str | None = None
    tool_status: str | None = None

    permission_status: str = "-"
    verification_status: str = "-"

    memory_hits: int = 0

    current_step: int = 0
    total_steps: int = 0

    planner_calls: int = 0

    last_latency_seconds: float | None = None
    request_started_at: float | None = None

    last_error: str | None = None

    provider_statuses: dict[str, str] = field(
        default_factory=dict
    )

    history: list[str] = field(
        default_factory=list
    )

    debug_events: list[str] = field(
        default_factory=list
    )

    def reset_runtime(self) -> None:
        self.phase = "idle"
        self.activity = "In attesa..."
        self.detail = ""

        self.input_tokens = None
        self.output_tokens = None
        self.total_tokens = None

        self.context_tokens = None
        self.context_limit = None

        self.tool_name = None
        self.tool_status = None

        self.permission_status = "-"
        self.verification_status = "-"

        self.memory_hits = 0

        self.current_step = 0
        self.total_steps = 0

        self.planner_calls = 0

        self.last_latency_seconds = None
        self.request_started_at = None

        self.last_error = None

        self.history.clear()

    def apply(
        self,
        event: IRISEvent,
    ) -> None:
        name = event.name
        data = event.data

        self.debug_events.append(
            self._format_debug_event(event)
        )

        if len(self.debug_events) > 50:
            self.debug_events.pop(0)

        if name == "core.chat.started":
            self.phase = "thinking"
            self.activity = "Sto elaborando..."
            self.detail = str(
                data.get("message", "")
            )
            self.task = "general"
            self.request_started_at = monotonic()
            self.last_error = None
            return

        if name == "core.chat.completed":
            self.phase = "done"
            self.activity = "Risposta completata."
            self.detail = ""
            self.last_latency_seconds = data.get(
                "latency_seconds"
            )
            self._push_history(
                "✓ Risposta completata"
            )
            return

        if name == "memory.started":
            self.phase = "memory"
            self.activity = "Recuperando memoria..."
            self.detail = ""
            return

        if name == "memory.completed":
            count = data.get(
                "count",
                0,
            )

            if isinstance(count, int):
                self.memory_hits = count

            self._push_history(
                f"✓ Memoria recuperata: {self.memory_hits}"
            )

            return

        if name == "memory.extraction.started":
            self.phase = "memory"
            self.activity = "Controllando nuove memorie..."
            self.detail = ""
            return

        if name == "memory.extraction.completed":
            count = data.get(
                "count",
                0,
            )

            self._push_history(
                f"✓ Candidati memoria: {count}"
            )

            return

        if name == "planner.started":
            self.phase = "planning"
            self.activity = "Pianificando..."
            self.detail = str(
                data.get("goal", "")
            )
            self.task = "agent"

            self.current_step = 0
            self.total_steps = 0

            return

        if name == "planner.completed":
            self.total_steps = int(
                data.get(
                    "steps",
                    0,
                )
                or 0
            )

            self.planner_calls = int(
                data.get(
                    "planner_calls",
                    self.planner_calls,
                )
                or self.planner_calls
            )

            self.activity = (
                f"Piano creato · "
                f"{self.total_steps} step"
            )

            self._push_history(
                "✓ Piano creato"
            )

            return

        if name == "agent.started":
            self.phase = "thinking"
            self.activity = "Analizzando obiettivo..."
            self.detail = str(
                data.get("goal", "")
            )
            self.task = "agent"
            self.request_started_at = monotonic()
            self.last_error = None
            return

        if name == "agent.completed":
            self.phase = "done"

            decision = str(
                data.get(
                    "decision",
                    "done",
                )
            )

            self.activity = (
                "Operazione completata."
                if decision == "done"
                else "Operazione terminata."
            )

            self.last_latency_seconds = data.get(
                "total_seconds"
            )

            self._push_history(
                f"✓ Agent completato · {decision}"
            )

            return

        if name == "llm.started":
            self.provider = str(
                data.get(
                    "provider",
                    self.provider,
                )
            )

            self.model = str(
                data.get(
                    "model",
                    self.model,
                )
            )

            self.task = str(
                data.get(
                    "task",
                    self.task,
                )
            )

            context_limit = data.get(
                "context_window"
            )

            if isinstance(
                context_limit,
                int,
            ):
                self.context_limit = context_limit

            if self.phase not in {
                "planning",
                "memory",
            }:
                self.phase = "thinking"

                if self.task == "agent":
                    self.activity = "Elaborando piano..."
                else:
                    self.activity = "Generando risposta..."

            self.request_started_at = monotonic()
            self.last_error = None
            return

        if name == "llm.completed":
            usage = data.get(
                "usage"
            )

            if isinstance(
                usage,
                dict,
            ):
                self.input_tokens = self._safe_int(
                    usage.get("input_tokens")
                )

                self.output_tokens = self._safe_int(
                    usage.get("output_tokens")
                )

                total = self._safe_int(
                    usage.get("total_tokens")
                )

                if total is None:
                    input_tokens = self.input_tokens or 0
                    output_tokens = self.output_tokens or 0

                    if input_tokens or output_tokens:
                        total = (
                            input_tokens
                            + output_tokens
                        )

                self.total_tokens = total

                if self.input_tokens is not None:
                    self.context_tokens = (
                        self.input_tokens
                    )

            self.last_latency_seconds = self._safe_float(
                data.get(
                    "latency_seconds"
                )
            )

            self.phase = (
                "planning"
                if self.task == "agent"
                else "thinking"
            )

            return

        if name == "llm.error":
            self.phase = "error"
            self.activity = "Errore LLM"
            self.detail = str(
                data.get(
                    "message",
                    "",
                )
            )

            self.last_error = self.detail

            self._push_history(
                f"✗ {self.provider}: {self.detail}"
            )

            return

        if name == "provider.disabled":
            provider = str(
                data.get(
                    "provider",
                    "?",
                )
            )

            category = str(
                data.get(
                    "category",
                    "disabled",
                )
            )

            self.provider_statuses[
                provider
            ] = category

            return

        if name == "tool.started":
            self.phase = "tool"
            self.activity = "Eseguendo..."
            self.tool_name = str(
                data.get(
                    "tool",
                    "?",
                )
            )
            self.tool_status = "running"

            self.current_step = int(
                data.get(
                    "step",
                    self.current_step,
                )
                or self.current_step
            )

            self.permission_status = (
                "in attesa"
            )

            self._push_history(
                f"▶ {self.tool_name}"
            )

            return

        if name == "permission.checked":
            granted = bool(
                data.get(
                    "granted",
                    False,
                )
            )

            self.permission_status = (
                "✓ autorizzato"
                if granted
                else "✗ negato"
            )

            self.activity = (
                "Controllo permessi completato."
            )

            return

        if name == "tool.completed":
            success = bool(
                data.get(
                    "success",
                    False,
                )
            )

            self.tool_status = (
                "success"
                if success
                else "error"
            )

            self.activity = (
                "Tool completato."
                if success
                else "Tool terminato con errore."
            )

            self._push_history(
                (
                    "✓ "
                    if success
                    else "✗ "
                )
                + str(
                    data.get(
                        "tool",
                        self.tool_name or "?",
                    )
                )
            )

            return

        if name == "verification.started":
            self.phase = "verification"
            self.activity = "Verificando risultato..."
            self.verification_status = (
                "in corso"
            )
            return

        if name == "verification.completed":
            verified = bool(
                data.get(
                    "verified",
                    False,
                )
            )

            self.verification_status = (
                "✓ verificato"
                if verified
                else "✗ non verificato"
            )

            self.activity = (
                "Risultato verificato."
                if verified
                else "Verifica fallita."
            )

            return

        if name == "router.fallback":
            provider = str(
                data.get(
                    "provider",
                    "?",
                )
            )

            category = str(
                data.get(
                    "category",
                    "unknown",
                )
            )

            next_provider = str(
                data.get(
                    "next_provider",
                    "?",
                )
            )

            self.activity = "Cambio provider..."
            self.detail = (
                f"{provider} → {next_provider} "
                f"({category})"
            )

            self._push_history(
                (
                    "↪ fallback "
                    f"{provider} → {next_provider}"
                )
            )

            return

    def _push_history(
        self,
        value: str,
    ) -> None:
        self.history.append(value)

        if len(self.history) > 8:
            self.history.pop(0)

    @staticmethod
    def _safe_int(
        value: Any,
    ) -> int | None:
        if isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            int,
        ):
            return value

        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> float | None:
        if isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            (int, float),
        ):
            return float(value)

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _format_debug_event(
        event: IRISEvent,
    ) -> str:
        if not event.data:
            return event.name

        parts = []

        for key, value in event.data.items():
            if key in {
                "messages",
                "response",
                "raw",
                "payload",
            }:
                continue

            text = str(value)

            if len(text) > 120:
                text = text[:117] + "..."

            parts.append(
                f"{key}={text}"
            )

        if not parts:
            return event.name

        return (
            event.name
            + " | "
            + ", ".join(parts)
        )
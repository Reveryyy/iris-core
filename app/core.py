import json
import os
import subprocess
from time import perf_counter
from typing import Any

from app.agent.loop import AgentLoop, AgentLoopResult
from app.llm.router import LLMRouter
from app.memory.context import ContextBuilder
from app.memory.conversation import Conversation
from app.memory.extractor import MemoryExtractor
from app.memory.service import MemoryService
from app.personality.manager import PersonalityManager
from app.tools.core import CoreToolHandler
from app.ui.events import IRISEventBus


class IRISCore:

    MAX_TOOL_ROUNDS = 4

    def __init__(
        self,
        router: LLMRouter,
        memory: MemoryService,
        tool_handler: CoreToolHandler | None = None,
        agent_loop: AgentLoop | None = None,
        event_bus: IRISEventBus | None = None,
    ):
        self.router = router
        self.memory = memory

        self.conversation = Conversation()
        self.context_builder = ContextBuilder()

        self.memory_extractor = MemoryExtractor(
            router=self.router,
        )

        self.personality = PersonalityManager()

        self.tool_handler = tool_handler
        self.agent_loop = agent_loop

        self.event_bus = (
            event_bus
            or IRISEventBus()
        )

        self._recent_agent_state: list[dict[str, Any]] = []

    def chat(
        self,
        message: str,
        confirmed: bool = False,
    ) -> str:

        started = perf_counter()

        self.event_bus.emit(
            "core.chat.started",
            message=message,
        )

        self.conversation.add_user_message(
            message
        )

        self._processo_memory_candidates(
            message
        )

        if self.tool_handler is None:
            result = self._generate_normal_response(
                message
            )

            self.event_bus.emit(
                "core.chat.completed",
                latency_seconds=(
                    perf_counter()
                    - started
                ),
            )

            return result

        result = self._generate_with_tools(
            message=message,
            confirmed=confirmed,
        )

        self.event_bus.emit(
            "core.chat.completed",
            latency_seconds=(
                perf_counter()
                - started
            ),
        )

        return result

    def run_agent(
        self,
        goal: str,
        confirmed: bool = False,
    ) -> AgentLoopResult:

        if self.agent_loop is None:
            raise RuntimeError(
                "Agent Loop non configurato."
            )

        if not isinstance(
            goal,
            str,
        ):
            raise TypeError(
                "L'obiettivo dell'agente deve essere una stringa."
            )

        if not goal.strip():
            raise ValueError(
                "L'obiettivo dell'agente non può essere vuoto."
            )

        self.conversation.add_user_message(
            goal
        )

        self._processo_memory_candidates(
            goal
        )

        context = self._build_agent_context(
            goal
        )

        tool_definitions = (
            self._get_agent_registry()
            .definitions()
        )

        result = self.agent_loop.run(
            goal=goal,
            context=context,
            tool_definitions=tool_definitions,
            confirmed=confirmed,
        )

        self._remember_agent_result(
            result
        )

        self.conversation.add_assistant_message(
            result.message
        )

        return result

    def _build_agent_context(
        self,
        goal: str,
    ) -> str:

        self.event_bus.emit(
            "memory.started",
            operation="agent_context",
        )

        memories = self.memory.search_semantic(
            goal,
            limit=5,
        )

        self.event_bus.emit(
            "memory.completed",
            count=len(memories),
            operation="agent_context",
        )

        memory_context = (
            self.context_builder.build_memory_context(
                memories
            )
        )

        preferences = self.memory.search_by_type(
            "preference"
        )

        personality_context = (
            self.personality.build_context(
                message=goal,
                preferences=preferences,
            )
        )

        parts: list[str] = []

        runtime_context = self._build_runtime_agent_context()
        recent_agent_context = self._build_recent_agent_context()

        if recent_agent_context:
            parts.append(
                recent_agent_context
            )

        if runtime_context:
            parts.append(
                runtime_context
            )

        if personality_context:
            parts.append(
                "PERSONALITÀ E CONTESTO:\n"
                + personality_context
            )

        if memory_context:
            parts.append(
                memory_context
            )

        return "\n\n".join(
            parts
        )

    def _build_recent_agent_context(self) -> str:
        """Espone al Planner gli ultimi risultati agent verificati."""
        if not self._recent_agent_state:
            return ""

        lines = [
            "STATO OPERATIVO RECENTE:",
            "Le osservazioni seguenti derivano da azioni già eseguite e verificate "
            "nelle richieste agent precedenti. Usale come stato reale del PC e "
            "come riferimento per espressioni come 'quella cartella' o 'quel file'.",
        ]

        for observation in reversed(self._recent_agent_state):
            lines.append(
                json.dumps(
                    observation,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        return "\\n".join(lines)

    @staticmethod
    def _build_runtime_agent_context() -> str:
        """
        Espone al Planner informazioni ambientali reali del processo.

        Il contesto non impone allowlist o percorsi: fornisce soltanto
        coordinate di partenza che il sistema operativo conosce già.
        """
        cwd = os.getcwd()
        lines = [
            "AMBIENTE REALE DEL PROCESSO:",
            f"- DIRECTORY DI LAVORO CORRENTE: {cwd}",
        ]

        try:
            completed = subprocess.run(
                [
                    "git",
                    "rev-parse",
                    "--show-toplevel",
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
                stdin=subprocess.DEVNULL,
                shell=False,
            )
        except (
            OSError,
            subprocess.SubprocessError,
        ):
            completed = None

        if completed is not None and completed.returncode == 0:
            git_root = completed.stdout.strip()

            if git_root:
                lines.append(
                    f"- RADICE GIT DEL PROGETTO: {git_root}"
                )

        return "\\n".join(lines)

    def _remember_agent_result(
        self,
        result: AgentLoopResult,
    ) -> None:

        for step_result in result.steps:

            if not step_result.verification.verified:
                continue

            tool_result = step_result.tool_result

            self._recent_agent_state.append(
                {
                    "tool_name": step_result.tool_call.name,
                    "arguments": step_result.tool_call.arguments,
                    "output": tool_result.output,
                }
            )

            output = (
                tool_result.output
                if tool_result.output is not None
                else ""
            )

            content = (
                f"Azione agente verificata: "
                f"{step_result.tool_call.name}."
            )

            if output:
                content += (
                    f" Risultato: {output}"
                )

            self.memory.remember(
                content=content,
                memory_type="agent_event",
                importance=1,
                confidence=1.0,
                source="agent_loop",
            )

    def _generate_normal_response(
        self,
        message: str,
    ) -> str:

        messages = self._build_messages(
            message
        )

        response = self.router.generate(
            messages
        )

        response = self._decode_final_response(
            response
        )

        self.conversation.add_assistant_message(
            response
        )

        return response

    def _generate_with_tools(
        self,
        message: str,
        confirmed: bool,
    ) -> str:

        tools = self._get_provider_tools()

        for _ in range(
            self.MAX_TOOL_ROUNDS
        ):

            messages = self._build_messages(
                message
            )

            response = self.router.generate(
                messages,
                tools=tools,
            )

            tool_response = (
                self.tool_handler.handle_response(
                    response=response,
                    confirmed=confirmed,
                )
            )

            if tool_response.protocol_error is not None:
                error_message = (
                    "Errore: la risposta del modello "
                    "non rispetta il protocollo richiesto."
                )

                self.conversation.add_assistant_message(
                    error_message
                )

                return error_message

            if not tool_response.is_tool_call:

                final_response = (
                    tool_response.response
                    or ""
                )

                self.conversation.add_assistant_message(
                    final_response
                )

                return final_response

            tool_call = tool_response.tool_call

            if tool_call is None:
                error_message = (
                    "Errore: il Tool System ha ricevuto "
                    "una tool call non valida."
                )

                self.conversation.add_assistant_message(
                    error_message
                )

                return error_message

            self.event_bus.emit(
                "permission.checked",
                tool=tool_call.name,
                granted=confirmed or True,
            )

            self.event_bus.emit(
                "tool.started",
                tool=tool_call.name,
                step=1,
                arguments=tool_call.arguments,
            )

            tool_call_id = tool_call.call_id

            if tool_call_id is None:
                error_message = (
                    "Errore: il modello non ha fornito "
                    "un identificativo per la tool call."
                )

                self.conversation.add_assistant_message(
                    error_message
                )

                return error_message

            self.conversation.add_tool_call(
                content=None,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                tool_call_id=tool_call_id,
            )

            tool_result = (
                tool_response.tool_result
            )

            if tool_result is None:
                self.event_bus.emit(
                    "tool.completed",
                    tool=tool_call.name,
                    step=1,
                    success=False,
                    error="Nessun risultato ricevuto.",
                )

                self.conversation.add_tool_result(
                    content=(
                        "success=false; "
                        "error=Nessun risultato ricevuto "
                        "dal Tool System."
                    ),
                    tool_name=tool_call.name,
                    tool_call_id=tool_call_id,
                )

                continue

            self.event_bus.emit(
                "tool.completed",
                tool=tool_call.name,
                step=1,
                success=tool_result.success,
                output=tool_result.output,
                error=tool_result.error,
            )

            self.conversation.add_tool_result(
                content=self._serialize_tool_result(
                    tool_result
                ),
                tool_name=tool_call.name,
                tool_call_id=tool_call_id,
            )

        error_message = (
            "Mi sono fermata perché sono stati "
            "raggiunti i limiti consecutivi "
            "di utilizzo dei tool."
        )

        self.conversation.add_assistant_message(
            error_message
        )

        return error_message

    def _get_provider_tools(
        self,
    ) -> list[dict[str, Any]]:

        registry = self._get_registry()

        tools: list[dict[str, Any]] = []

        for definition in registry.definitions():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": definition[
                            "name"
                        ],
                        "description": definition[
                            "description"
                        ],
                        "parameters": definition[
                            "input_schema"
                        ],
                    },
                }
            )

        return tools

    def _serialize_tool_result(
        self,
        result,
    ) -> str:

        if result.success:
            return (
                "success=true; "
                f"output={result.output!r}"
            )

        return (
            "success=false; "
            f"error={result.error!r}"
        )

    def _decode_final_response(
        self,
        response: str,
    ) -> str:

        try:
            data = json.loads(
                response
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return response

        if data.get("type") == "final":
            return (
                data.get("content")
                or ""
            )

        return response

    def _build_messages(
        self,
        message: str,
    ) -> list[dict[str, Any]]:

        messages = (
            self.conversation.to_provider_messages()
        )

        self.event_bus.emit(
            "memory.started",
            operation="chat_context",
        )

        memories = self.memory.search_semantic(
            message,
            limit=5,
        )

        self.event_bus.emit(
            "memory.completed",
            count=len(memories),
            operation="chat_context",
        )

        memory_context = (
            self.context_builder.build_memory_context(
                memories
            )
        )

        preferences = self.memory.search_by_type(
            "preference"
        )

        personality_context = (
            self.personality.build_context(
                message=message,
                preferences=preferences,
            )
        )

        system_context = personality_context

        if memory_context:
            system_context += (
                "\n\n"
                + memory_context
            )

        if self.tool_handler is not None:

            system_context += (
                "\n\n"
                "REGOLE TOOL:\n"
                "- Usa esclusivamente i tool forniti "
                "dal sistema.\n"
                "- Un tool presente nelle definizioni "
                "fornite dal sistema esiste realmente.\n"
                "- Un tool assente dalle definizioni "
                "fornite dal sistema non è disponibile.\n"
                "- Non confondere un tool disponibile con "
                "un comando o una funzione generica del "
                "linguaggio.\n"
                "- Non inventare tool, risultati o argomenti.\n"
                "- Non dichiarare mai di aver eseguito "
                "un'azione se non esiste una tool call "
                "corrispondente e un risultato del Tool System.\n"
                "- Se un tool restituisce un errore, "
                "usa quell'errore come fonte di verità.\n"
            )

            registry = self._get_registry()

            definitions = registry.definitions()

            if definitions:

                system_context += (
                    "\nTOOL DISPONIBILI:\n"
                )

                for definition in definitions:

                    system_context += (
                        f"- {definition['name']}: "
                        f"{definition['description']}\n"
                    )

                    schema = definition[
                        "input_schema"
                    ]

                    required = schema.get(
                        "required",
                        [],
                    )

                    if required:
                        system_context += (
                            "  Argomenti obbligatori: "
                            + ", ".join(required)
                            + "\n"
                        )

        messages.insert(
            0,
            {
                "role": "system",
                "content": system_context,
            },
        )

        return messages

    def _get_registry(self):
        if self.tool_handler is None:
            raise RuntimeError(
                "Tool System non configurato."
            )

        return (
            self.tool_handler
            .execution_service
            .dispatcher
            .registry
        )

    def _get_agent_registry(self):
        if self.agent_loop is None:
            raise RuntimeError(
                "Agent Loop non configurato."
            )

        return (
            self.agent_loop
            .execution_service
            .dispatcher
            .registry
        )

    def _processo_memory_candidates(
        self,
        message: str,
    ) -> None:

        self.event_bus.emit(
            "memory.extraction.started"
        )

        candidates = self.memory_extractor.extract(
            message
        )

        self.event_bus.emit(
            "memory.extraction.completed",
            count=len(candidates),
        )

        for candidate in candidates:
            self.memory.remember(
                content=candidate.content,
                memory_type=candidate.memory_type,
                importance=candidate.importance,
                confidence=candidate.confidence,
                source=candidate.source,
            )

    def remember(
        self,
        content: str,
        memory_type: str,
        importance: int = 1,
        confidence: float = 1.0,
        source: str = "user",
    ) -> int | None:

        return self.memory.remember(
            content=content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            source=source,
        )

    def recall(
        self,
        memory_id: int,
    ) -> str | None:

        return self.memory.recall(
            memory_id
        )
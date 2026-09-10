import json
from dataclasses import dataclass
from typing import Any

from app.agent.decision import AgentDecision
from app.agent.observation import AgentObservation
from app.llm.router import LLMRouter


@dataclass(frozen=True)
class AgentPlanStep:
    tool_name: str
    arguments: dict[str, Any]
    description: str
    success_criteria: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.tool_name,
            str,
        ):
            raise TypeError(
                "Il nome del tool del piano deve essere una stringa."
            )

        if not self.tool_name.strip():
            raise ValueError(
                "Il nome del tool del piano non può essere vuoto."
            )

        if not isinstance(
            self.arguments,
            dict,
        ):
            raise TypeError(
                "Gli argomenti del piano devono essere un dizionario."
            )

        if not isinstance(
            self.description,
            str,
        ):
            raise TypeError(
                "La descrizione dello step deve essere una stringa."
            )

        if not self.description.strip():
            raise ValueError(
                "La descrizione dello step non può essere vuota."
            )

        if (
            self.success_criteria is not None
            and not isinstance(
                self.success_criteria,
                str,
            )
        ):
            raise TypeError(
                "I criteri di successo devono essere una stringa oppure None."
            )


@dataclass(frozen=True)
class AgentPlan:
    goal: str
    steps: tuple[AgentPlanStep, ...]
    decision: AgentDecision = AgentDecision.DONE
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.goal,
            str,
        ):
            raise TypeError(
                "L'obiettivo del piano deve essere una stringa."
            )

        if not self.goal.strip():
            raise ValueError(
                "L'obiettivo del piano non può essere vuoto."
            )

        if not isinstance(
            self.steps,
            tuple,
        ):
            raise TypeError(
                "Gli step del piano devono essere una tupla."
            )

        if not self.steps:
            raise ValueError(
                "Il piano deve contenere almeno uno step."
            )

        for step in self.steps:
            if not isinstance(
                step,
                AgentPlanStep,
            ):
                raise TypeError(
                    "Ogni elemento del piano deve essere un AgentPlanStep."
                )

        if not isinstance(
            self.decision,
            AgentDecision,
        ):
            raise TypeError(
                "La decisione del piano deve essere un AgentDecision."
            )

        if (
            self.message is not None
            and not isinstance(
                self.message,
                str,
            )
        ):
            raise TypeError(
                "Il messaggio del piano deve essere una stringa oppure None."
            )


class AgentPlanner:
    """
    Genera o rigenera un piano strutturato per raggiungere un obiettivo.

    Il planner non esegue tool.

    Decisioni:
    - DONE: il piano raggiunge l'obiettivo;
    - CONTINUE: dopo gli step serve nuovo planning;
    - ASK_USER: serve l'intervento dell'utente.
    """

    PLAN_SCHEMA = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
            },
            "decision": {
                "type": "string",
                "enum": [
                    "done",
                    "continue",
                    "ask_user",
                ],
            },
            "message": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                        },
                        "arguments": {
                            "type": "object",
                        },
                        "description": {
                            "type": "string",
                        },
                        "success_criteria": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },
                    },
                    "required": [
                        "tool_name",
                        "arguments",
                        "description",
                    ],
                    "additionalProperties": False,
                },
                "minItems": 1,
            },
        },
        "required": [
            "goal",
            "steps",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        router: LLMRouter,
    ):
        self.router = router

    def plan(
        self,
        goal: str,
        context: str | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
        observations: list[AgentObservation] | None = None,
    ) -> AgentPlan:

        if not isinstance(
            goal,
            str,
        ):
            raise TypeError(
                "L'obiettivo deve essere una stringa."
            )

        if not goal.strip():
            raise ValueError(
                "L'obiettivo non può essere vuoto."
            )

        system_content = (
            "Sei il Planner di IRIS.\n"
            "Crea il minimo piano necessario per raggiungere "
            "l'obiettivo.\n"
            "Rispondi SOLO con un singolo oggetto JSON valido.\n"
            "Nessun markdown. Nessun testo fuori dal JSON.\n\n"
            "Formato:\n"
            '{"goal":"...","decision":"done","message":null,'
            '"steps":[{"tool_name":"...",'
            '"arguments":{},'
            '"description":"...",'
            '"success_criteria":"..."}]}\n\n'
            "Regole:\n"
            "- usa solo tool disponibili;\n"
            "- non inventare tool;\n"
            "- non inventare argomenti;\n"
            "- usa il minimo numero di step;\n"
            "- se basta un tool usa un solo step;\n"
            "- done = obiettivo completato;\n"
            "- continue = serve nuovo planning;\n"
            "- ask_user = serve l'utente;\n"
            "- non inventare risultati."
        )

        if tool_definitions:
            system_content += (
                "\n\nTOOL DISPONIBILI:\n"
                + self._build_compact_tool_context(
                    tool_definitions
                )
            )

        if context:
            compact_context = self._compact_text(
                context,
                max_chars=1000,
            )

            if compact_context:
                system_content += (
                    "\n\nCONTESTO:\n"
                    + compact_context
                )

        if observations:
            system_content += (
                "\n\nOSSERVAZIONI:\n"
                + self._build_compact_observations(
                    observations
                )
            )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": goal,
            },
        ]

        response = self.router.generate(
            messages,
            max_tokens=256,
            temperature=0.0,
        )

        data = self._decode_response(
            response
        )

        data = self._normalize_plan(
            data=data,
            fallback_goal=goal,
        )

        return self._build_plan(
            goal=goal,
            data=data,
        )

    @staticmethod
    def _compact_text(
        value: str,
        max_chars: int,
    ) -> str:

        if not isinstance(
            value,
            str,
        ):
            return ""

        value = value.strip()

        if not value:
            return ""

        if len(value) <= max_chars:
            return value

        return (
            value[:max_chars]
            + "\n[contesto troncato]"
        )

    @staticmethod
    def _build_compact_tool_context(
        tool_definitions: list[dict[str, Any]],
    ) -> str:

        lines: list[str] = []

        for definition in tool_definitions:

            if not isinstance(
                definition,
                dict,
            ):
                continue

            name = definition.get(
                "name",
                "",
            )

            description = definition.get(
                "description",
                "",
            )

            schema = definition.get(
                "input_schema",
                {},
            )

            if not isinstance(
                name,
                str,
            ):
                continue

            if not name.strip():
                continue

            if not isinstance(
                description,
                str,
            ):
                description = ""

            compact_schema = json.dumps(
                schema,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            lines.append(
                f"- {name}: {description}; schema={compact_schema}"
            )

        return "\n".join(
            lines
        )

    @staticmethod
    def _build_compact_observations(
        observations: list[AgentObservation],
    ) -> str:

        lines: list[str] = []

        for observation in observations:

            line = (
                f"step={observation.step_index}; "
                f"tool={observation.tool_name}; "
                f"success={observation.success}; "
                f"verified={observation.verified}"
            )

            if observation.error:
                line += (
                    f"; error={observation.error}"
                )

            if observation.output is not None:
                output = str(
                    observation.output
                )

                output = AgentPlanner._compact_text(
                    output,
                    max_chars=300,
                )

                if output:
                    line += (
                        f"; output={output}"
                    )

            lines.append(
                line
            )

        return "\n".join(
            lines
        )

    def _build_user_prompt(
        self,
        goal: str,
        context: str | None,
        observations: list[AgentObservation] | None,
    ) -> str:

        # Context e observations sono già presenti nel
        # system prompt in forma compatta.
        # Qui inviamo soltanto l'obiettivo per evitare
        # di duplicare token nel prompt del modello.
        return goal

    def _decode_response(
        self,
        response: str,
    ) -> dict[str, Any]:

        if not isinstance(
            response,
            str,
        ):
            raise TypeError(
                "La risposta del planner deve essere una stringa."
            )

        content = response.strip()

        if not content:
            raise ValueError(
                "Il planner ha restituito una risposta vuota."
            )

        for _ in range(4):
            content = self._strip_markdown_json(
                content
            )

            parsed = self._parse_json_value(
                content
            )

            if isinstance(
                parsed,
                dict,
            ):
                response_type = parsed.get(
                    "type"
                )

                if response_type == "final":
                    inner_content = parsed.get(
                        "content"
                    )

                    if isinstance(
                        inner_content,
                        str,
                    ):
                        content = inner_content.strip()
                        continue

                    if isinstance(
                        inner_content,
                        dict,
                    ):
                        return inner_content

                    raise ValueError(
                        "La risposta final del planner "
                        "non contiene un contenuto valido."
                    )

                if self._looks_like_plan(
                    parsed
                ):
                    return parsed

                for key in (
                    "content",
                    "result",
                    "plan",
                    "response",
                    "output",
                ):
                    nested = parsed.get(
                        key
                    )

                    if isinstance(
                        nested,
                        dict,
                    ):
                        if self._looks_like_plan(
                            nested
                        ):
                            return nested

                    if isinstance(
                        nested,
                        str,
                    ) and nested.strip():
                        content = nested.strip()
                        break
                else:
                    return parsed

                continue

            if isinstance(
                parsed,
                str,
            ):
                content = parsed.strip()
                continue

            raise ValueError(
                "Il planner non ha restituito un JSON valido."
            )

        raise ValueError(
            "Il planner non ha restituito "
            "un oggetto JSON valido dopo la decodifica."
        )

    @staticmethod
    def _looks_like_plan(
        data: dict[str, Any],
    ) -> bool:

        return (
            "steps" in data
            or "actions" in data
            or "tool_name" in data
            or "tool" in data
            or "name" in data
        )

    @staticmethod
    def _strip_markdown_json(
        content: str,
    ) -> str:

        if not content.startswith(
            "```"
        ):
            return content

        lines = content.splitlines()

        if (
            lines
            and lines[0].strip().startswith(
                "```"
            )
        ):
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        return "\n".join(
            lines
        ).strip()

    @staticmethod
    def _parse_json_value(
        content: str,
    ) -> Any:

        try:
            return json.loads(
                content
            )

        except json.JSONDecodeError as error:
            json_start = content.find(
                "{"
            )

            json_end = content.rfind(
                "}"
            )

            if (
                json_start == -1
                or json_end <= json_start
            ):
                raise ValueError(
                    "Il planner non ha restituito "
                    "un JSON valido."
                ) from error

            try:
                return json.loads(
                    content[
                        json_start:json_end + 1
                    ]
                )

            except json.JSONDecodeError as nested_error:
                raise ValueError(
                    "Il planner non ha restituito "
                    "un JSON valido."
                ) from nested_error

    def _normalize_plan(
        self,
        data: dict[str, Any],
        fallback_goal: str,
    ) -> dict[str, Any]:

        normalized = dict(
            data
        )

        nested = self._find_plan_container(
            normalized
        )

        if nested is not None:
            merged = dict(
                nested
            )

            for key, value in normalized.items():
                if (
                    key not in {
                        "plan",
                        "result",
                        "action",
                    }
                    and key not in merged
                ):
                    merged[key] = value

            normalized = merged

        returned_goal = normalized.get(
            "goal",
            fallback_goal,
        )

        if not isinstance(
            returned_goal,
            str,
        ):
            returned_goal = fallback_goal

        normalized["goal"] = returned_goal

        normalized["decision"] = (
            self._normalize_decision(
                normalized.get(
                    "decision",
                    AgentDecision.DONE.value,
                )
            )
        )

        message = normalized.get(
            "message"
        )

        if (
            message is not None
            and not isinstance(
                message,
                str,
            )
        ):
            normalized["message"] = str(
                message
            )

        raw_steps = normalized.get(
            "steps"
        )

        if raw_steps is None:
            for key in (
                "actions",
                "action_steps",
                "operations",
                "tools",
            ):
                candidate = normalized.get(
                    key
                )

                if candidate is not None:
                    raw_steps = candidate
                    break

        normalized_steps = (
            self._normalize_steps_value(
                raw_steps
            )
        )

        if normalized_steps is None:
            candidate = (
                self._extract_step_from_anywhere(
                    normalized
                )
            )

            if candidate is not None:
                normalized_steps = [
                    candidate
                ]

        normalized_steps = (
            self._deduplicate_steps(
                normalized_steps
            )
        )

        normalized["steps"] = normalized_steps

        return normalized

    def _find_plan_container(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:

        for key in (
            "plan",
            "result",
            "action",
        ):
            value = data.get(
                key
            )

            if isinstance(
                value,
                str,
            ):
                parsed = self._parse_json_value(
                    value
                )

                if isinstance(
                    parsed,
                    dict,
                ):
                    value = parsed

            if isinstance(
                value,
                dict,
            ):
                if (
                    "steps" in value
                    or "actions" in value
                    or "tool_name" in value
                    or "tool" in value
                    or "name" in value
                    or "function" in value
                ):
                    return value

        return None

    def _normalize_steps_value(
        self,
        value: Any,
    ) -> list[Any] | None:

        if value is None:
            return None

        if isinstance(
            value,
            list,
        ):
            return value

        if isinstance(
            value,
            tuple,
        ):
            return list(
                value
            )

        if isinstance(
            value,
            dict,
        ):
            nested_steps = value.get(
                "steps"
            )

            if nested_steps is not None:
                normalized = (
                    self._normalize_steps_value(
                        nested_steps
                    )
                )

                if normalized:
                    return normalized

            candidate = self._step_from_dict(
                value
            )

            if candidate is not None:
                return [
                    candidate
                ]

            for key in (
                "actions",
                "action_steps",
                "operations",
                "tools",
                "items",
                "data",
            ):
                nested = value.get(
                    key
                )

                if nested is not None:
                    normalized = (
                        self._normalize_steps_value(
                            nested
                        )
                    )

                    if normalized:
                        return normalized

            for nested in value.values():
                normalized = (
                    self._normalize_steps_value(
                        nested
                    )
                )

                if normalized:
                    return normalized

            return None

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            if not text:
                return None

            parsed = self._parse_json_value(
                text
            )

            if parsed is not None:
                normalized = (
                    self._normalize_steps_value(
                        parsed
                    )
                )

                if normalized:
                    return normalized

            return [
                {
                    "tool_name": text,
                    "arguments": {},
                    "description": (
                        f"Esegui il tool {text}."
                    ),
                }
            ]

        return None

    @staticmethod
    def _deduplicate_steps(
        steps: list[Any] | None,
    ) -> list[Any] | None:

        if not steps:
            return steps

        result: list[Any] = []
        seen: set[str] = set()

        for step in steps:
            if isinstance(
                step,
                dict,
            ):
                tool_name = step.get(
                    "tool_name",
                    step.get(
                        "tool",
                        step.get(
                            "name",
                            "",
                        ),
                    ),
                )

                arguments = step.get(
                    "arguments",
                    step.get(
                        "args",
                        {},
                    ),
                )

                try:
                    key = json.dumps(
                        {
                            "tool_name": tool_name,
                            "arguments": arguments,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                except TypeError:
                    key = repr(
                        (
                            tool_name,
                            arguments,
                        )
                    )

                if key in seen:
                    continue

                seen.add(
                    key
                )

            result.append(
                step
            )

        return result

    def _extract_step_from_anywhere(
        self,
        value: Any,
    ) -> dict[str, Any] | None:

        if isinstance(
            value,
            dict,
        ):
            direct = self._step_from_dict(
                value
            )

            if direct is not None:
                return direct

            for nested_value in value.values():
                found = (
                    self._extract_step_from_anywhere(
                        nested_value
                    )
                )

                if found is not None:
                    return found

            return None

        if isinstance(
            value,
            list,
        ):
            for item in value:
                found = (
                    self._extract_step_from_anywhere(
                        item
                    )
                )

                if found is not None:
                    return found

            return None

        if isinstance(
            value,
            str,
        ):
            parsed = self._parse_json_value(
                value.strip()
            )

            if parsed is None:
                return None

            return self._extract_step_from_anywhere(
                parsed
            )

        return None

    def _step_from_dict(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:

        tool_name = data.get(
            "tool_name"
        )

        if not isinstance(
            tool_name,
            str,
        ):
            tool_name = data.get(
                "tool"
            )

        if not isinstance(
            tool_name,
            str,
        ):
            tool_name = data.get(
                "name"
            )

        if not isinstance(
            tool_name,
            str,
        ):
            function = data.get(
                "function"
            )

            if isinstance(
                function,
                dict,
            ):
                tool_name = function.get(
                    "name"
                )

        if not isinstance(
            tool_name,
            str,
        ):
            return None

        tool_name = tool_name.strip()

        if not tool_name:
            return None

        arguments = data.get(
            "arguments"
        )

        if arguments is None:
            arguments = data.get(
                "args",
                {},
            )

        if isinstance(
            arguments,
            str,
        ):
            parsed_arguments = (
                self._parse_json_value(
                    arguments
                )
            )

            if isinstance(
                parsed_arguments,
                dict,
            ):
                arguments = parsed_arguments

        if not isinstance(
            arguments,
            dict,
        ):
            arguments = {}

        function = data.get(
            "function"
        )

        if isinstance(
            function,
            dict,
        ):
            function_arguments = function.get(
                "arguments"
            )

            if isinstance(
                function_arguments,
                str,
            ):
                parsed_arguments = (
                    self._parse_json_value(
                        function_arguments
                    )
                )

                if isinstance(
                    parsed_arguments,
                    dict,
                ):
                    arguments = parsed_arguments

        description = data.get(
            "description",
            f"Esegui il tool {tool_name}.",
        )

        if not isinstance(
            description,
            str,
        ):
            description = (
                f"Esegui il tool {tool_name}."
            )

        success_criteria = data.get(
            "success_criteria"
        )

        if success_criteria is not None:
            success_criteria = str(
                success_criteria
            )

        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "description": description,
            "success_criteria": success_criteria,
        }

    @staticmethod
    def _normalize_decision(
        value: Any,
    ) -> str:

        if isinstance(
            value,
            AgentDecision,
        ):
            return value.value

        if not isinstance(
            value,
            str,
        ):
            return AgentDecision.DONE.value

        normalized = (
            value.strip().lower()
        )

        aliases = {
            "done": "done",
            "complete": "done",
            "completed": "done",
            "finish": "done",
            "finished": "done",
            "success": "done",
            "continue": "continue",
            "next": "continue",
            "keep_going": "continue",
            "keep-going": "continue",
            "ask_user": "ask_user",
            "ask-user": "ask_user",
            "ask user": "ask_user",
            "user": "ask_user",
        }

        return aliases.get(
            normalized,
            AgentDecision.DONE.value,
        )

    @staticmethod
    def _parse_json_value(
        value: str,
    ) -> Any:

        try:
            return json.loads(
                value
            )
        except json.JSONDecodeError:
            return None

    def _build_plan(
        self,
        goal: str,
        data: dict[str, Any],
    ) -> AgentPlan:

        returned_goal = data.get(
            "goal",
            goal,
        )

        if not isinstance(
            returned_goal,
            str,
        ):
            raise ValueError(
                "Il campo 'goal' del piano non è valido."
            )

        decision_value = data.get(
            "decision",
            AgentDecision.DONE.value,
        )

        if not isinstance(
            decision_value,
            str,
        ):
            raise ValueError(
                "Il campo 'decision' del piano non è valido."
            )

        try:
            decision = AgentDecision(
                decision_value
            )
        except ValueError as error:
            raise ValueError(
                "La decisione del piano non è valida."
            ) from error

        message = data.get(
            "message"
        )

        if (
            message is not None
            and not isinstance(
                message,
                str,
            )
        ):
            raise ValueError(
                "Il campo 'message' del piano non è valido."
            )

        steps_data = data.get(
            "steps"
        )

        if not isinstance(
            steps_data,
            list,
        ):
            raise ValueError(
                "Il planner non ha prodotto "
                "uno step recuperabile dal JSON restituito."
            )

        if not steps_data:
            raise ValueError(
                "Il planner ha restituito un piano vuoto."
            )

        steps: list[AgentPlanStep] = []

        for index, raw_step in enumerate(
            steps_data,
            start=1,
        ):
            if isinstance(
                raw_step,
                str,
            ):
                raw_step = {
                    "tool_name": raw_step,
                    "arguments": {},
                    "description": (
                        f"Esegui il tool {raw_step}."
                    ),
                }

            if not isinstance(
                raw_step,
                dict,
            ):
                raise ValueError(
                    f"Lo step {index} del piano non è valido."
                )

            tool_name = raw_step.get(
                "tool_name"
            )

            if not isinstance(
                tool_name,
                str,
            ):
                tool_name = raw_step.get(
                    "tool"
                )

            if not isinstance(
                tool_name,
                str,
            ):
                tool_name = raw_step.get(
                    "name"
                )

            if not isinstance(
                tool_name,
                str,
            ):
                function = raw_step.get(
                    "function"
                )

                if isinstance(
                    function,
                    dict,
                ):
                    tool_name = function.get(
                        "name"
                    )

            arguments = raw_step.get(
                "arguments"
            )

            if arguments is None:
                arguments = raw_step.get(
                    "args",
                    {},
                )

            if isinstance(
                arguments,
                str,
            ):
                parsed_arguments = (
                    self._parse_json_value(
                        arguments
                    )
                )

                if isinstance(
                    parsed_arguments,
                    dict,
                ):
                    arguments = parsed_arguments

            if arguments is None:
                arguments = {}

            description = raw_step.get(
                "description"
            )

            if description is None:
                if isinstance(
                    tool_name,
                    str,
                ):
                    description = (
                        f"Esegui il tool {tool_name}."
                    )

            success_criteria = raw_step.get(
                "success_criteria"
            )

            if (
                success_criteria is not None
                and not isinstance(
                    success_criteria,
                    str,
                )
            ):
                success_criteria = str(
                    success_criteria
                )

            if not isinstance(
                tool_name,
                str,
            ):
                raise ValueError(
                    f"Lo step {index} non contiene "
                    "un tool_name valido."
                )

            if not isinstance(
                arguments,
                dict,
            ):
                raise ValueError(
                    f"Gli argomenti dello step {index} "
                    "devono essere un oggetto."
                )

            if not isinstance(
                description,
                str,
            ):
                raise ValueError(
                    f"La descrizione dello step {index} "
                    "non è valida."
                )

            steps.append(
                AgentPlanStep(
                    tool_name=tool_name,
                    arguments=arguments,
                    description=description,
                    success_criteria=success_criteria,
                )
            )

        return AgentPlan(
            goal=returned_goal,
            steps=tuple(steps),
            decision=decision,
            message=message,
        )
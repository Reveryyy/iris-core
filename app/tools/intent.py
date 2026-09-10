import json
from typing import Any

from app.llm.router import LLMRouter


class ToolIntentResolver:
    """
    Determina quale tool, se presente, è richiesto dalla richiesta
    dell'utente.

    Viene usato come meccanismo di recupero quando il modello
    principale non produce una risposta utile durante una richiesta
    che potrebbe coinvolgere i tool.

    Non esegue tool e non assegna permessi.
    """

    def __init__(
        self,
        router: LLMRouter,
    ):
        self.router = router

    def resolve(
        self,
        message: str,
        definitions: list[dict[str, Any]],
    ) -> str | None:

        if not definitions:
            return None

        tool_names = [
            definition["name"]
            for definition in definitions
        ]

        response_format = {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "enum": tool_names + ["none"],
                    }
                },
                "required": ["tool_name"],
                "additionalProperties": False,
            },
        }

        available_tools = "\n".join(
            (
                f"- {definition['name']}: "
                f"{definition['description']}"
            )
            for definition in definitions
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Devi identificare se la richiesta "
                    "dell'utente riguarda uno dei tool disponibili.\n"
                    "Restituisci esclusivamente JSON valido secondo "
                    "lo schema fornito.\n"
                    "Scegli il nome esatto del tool se l'utente "
                    "sta chiedendo di usarlo.\n"
                    "Restituisci 'none' se nessun tool disponibile "
                    "è richiesto.\n"
                    "Non inventare tool.\n"
                    "Non eseguire azioni.\n\n"
                    "TOOL DISPONIBILI:\n"
                    f"{available_tools}"
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        try:
            response = self.router.generate(
                messages,
                response_format=response_format,
            )

            outer = json.loads(response)

            if not isinstance(outer, dict):
                return None

            content = outer.get("content")

            if not isinstance(content, str):
                return None

            data = json.loads(content)

            if not isinstance(data, dict):
                return None

            tool_name = data.get("tool_name")

            if tool_name == "none":
                return None

            if tool_name not in tool_names:
                return None

            return tool_name

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
            KeyError,
        ):
            return None
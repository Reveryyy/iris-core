import json
from typing import Any

from app.tools.call import ToolCall


class ToolCallParser:
    """
    Interpreta l'output strutturato del modello.

    Formato moderno:

    {
        "type": "tool_call",
        "name": "echo",
        "arguments": {
            "text": "Ciao"
        },
        "call_id": "call_123"
    }

    oppure:

    {
        "type": "final",
        "content": "Ciao!"
    }

    Viene mantenuta la compatibilità con il vecchio formato
    diretto:

    {
        "name": "echo",
        "arguments": {
            "text": "Ciao"
        }
    }
    """

    def parse(
        self,
        response: str,
    ) -> ToolCall:
        data = self._parse_json(
            response
        )

        if not isinstance(data, dict):
            raise ValueError(
                "La risposta del modello deve essere "
                "un oggetto JSON."
            )

        response_type = data.get("type")

        if response_type == "final":
            raise ValueError(
                "La risposta del modello è una risposta finale."
            )

        if response_type not in (
            None,
            "tool_call",
        ):
            raise ValueError(
                "Tipo di risposta del modello non valido."
            )

        tool_data = {
            "name": data.get("name"),
            "arguments": data.get("arguments"),
            "call_id": data.get("call_id"),
        }

        return ToolCall.from_dict(
            tool_data
        )

    def parse_response(
        self,
        response: str,
    ) -> tuple[str, ToolCall | None]:
        data = self._parse_json(
            response
        )

        if not isinstance(data, dict):
            raise ValueError(
                "La risposta del modello deve essere "
                "un oggetto JSON."
            )

        response_type = data.get("type")

        if response_type == "final":
            content = data.get("content")

            if not isinstance(content, str):
                raise ValueError(
                    "Una risposta final deve contenere "
                    "un campo 'content' stringa."
                )

            return content, None

        if response_type == "tool_call":
            tool_call = ToolCall.from_dict(
                {
                    "name": data.get("name"),
                    "arguments": data.get("arguments"),
                    "call_id": data.get("call_id"),
                }
            )

            return "", tool_call

        if response_type is None:
            tool_call = ToolCall.from_dict(
                data
            )

            return "", tool_call

        raise ValueError(
            "Tipo di risposta del modello non valido."
        )

    def _parse_json(
        self,
        response: str,
    ) -> Any:
        if not isinstance(response, str):
            raise TypeError(
                "La risposta del modello deve essere una stringa."
            )

        content = response.strip()

        if not content:
            raise ValueError(
                "La risposta del modello è vuota."
            )

        content = self._remove_markdown_code_block(
            content
        )

        try:
            return json.loads(
                content
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                "La risposta del modello non contiene "
                "un JSON valido."
            ) from error

    def _remove_markdown_code_block(
        self,
        content: str,
    ) -> str:
        if not content.startswith("```"):
            return content

        lines = content.splitlines()

        if len(lines) < 3:
            return content

        if lines[-1].strip() != "```":
            return content

        first_line = lines[0].strip().lower()

        if first_line not in (
            "```",
            "```json",
        ):
            return content

        return "\n".join(
            lines[1:-1]
        ).strip()
from __future__ import annotations

import json
import os
from typing import Any

import requests

from app.llm.errors import (
    classify_exception,
    classify_http_error,
)
from app.llm.provider import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key_env: str,
        model: str,
        timeout: float = 120.0,
        strict_structured_outputs: bool = False,
        context_window: int | None = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout = timeout
        self.strict_structured_outputs = (
            strict_structured_outputs
        )

        self.context_window = context_window

        self.last_usage: dict[str, int] | None = None

        api_key = os.getenv(
            api_key_env
        )

        if not api_key:
            raise RuntimeError(
                f"La variabile {api_key_env} non è configurata."
            )

        self.api_key = api_key

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 512,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:

        self.last_usage = None

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if response_format is not None:
            payload["response_format"] = (
                self._normalize_response_format(
                    response_format
                )
            )

        if tools is not None:
            payload["tools"] = tools

            if tools:
                payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )

        except Exception as error:
            raise classify_exception(
                provider=self.name,
                error=error,
            ) from error

        if not response.ok:
            try:
                payload_error = response.json()
            except ValueError:
                payload_error = None

            raise classify_http_error(
                provider=self.name,
                status_code=response.status_code,
                payload=payload_error,
                response_text=response.text,
            )

        try:
            data = response.json()

        except ValueError as error:
            raise RuntimeError(
                f"{self.name} ha restituito una risposta "
                "non JSON."
            ) from error

        usage = data.get(
            "usage"
        )

        if isinstance(
            usage,
            dict,
        ):
            self.last_usage = self._normalize_usage(
                usage
            )

        choices = data.get(
            "choices"
        )

        if not isinstance(
            choices,
            list,
        ) or not choices:
            raise RuntimeError(
                f"{self.name} non ha restituito alcuna scelta."
            )

        message = choices[0].get(
            "message"
        )

        if not isinstance(
            message,
            dict,
        ):
            raise RuntimeError(
                f"{self.name} ha restituito un messaggio non valido."
            )

        tool_calls = message.get(
            "tool_calls"
        )

        if tool_calls:
            return self._normalize_tool_call(
                tool_calls
            )

        content = message.get(
            "content"
        )

        if content is None:
            content = ""

        if isinstance(
            content,
            list,
        ):
            content = self._extract_content_blocks(
                content
            )

        if not isinstance(
            content,
            str,
        ):
            raise RuntimeError(
                f"{self.name} ha restituito un contenuto non valido."
            )

        return json.dumps(
            {
                "type": "final",
                "content": content,
                "name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )

    def _normalize_response_format(
        self,
        response_format: dict[str, Any],
    ) -> dict[str, Any]:

        response_type = response_format.get(
            "type"
        )

        if response_type != "json_object":
            return response_format

        schema = response_format.get(
            "schema"
        )

        if (
            schema is None
            or not self.strict_structured_outputs
        ):
            return {
                "type": "json_object",
            }

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "iris_structured_output",
                "strict": True,
                "schema": schema,
            },
        }

    def _normalize_tool_call(
        self,
        tool_calls: Any,
    ) -> str:

        if not isinstance(
            tool_calls,
            list,
        ) or not tool_calls:
            raise RuntimeError(
                f"{self.name} ha restituito una tool call vuota."
            )

        call = tool_calls[0]

        if not isinstance(
            call,
            dict,
        ):
            raise RuntimeError(
                f"{self.name} ha restituito una tool call non valida."
            )

        function = call.get(
            "function"
        )

        if not isinstance(
            function,
            dict,
        ):
            raise RuntimeError(
                f"{self.name} ha restituito una funzione tool non valida."
            )

        name = function.get(
            "name"
        )

        if not isinstance(
            name,
            str,
        ) or not name.strip():
            raise RuntimeError(
                f"{self.name} ha restituito un nome tool non valido."
            )

        arguments = function.get(
            "arguments",
            "{}",
        )

        if isinstance(
            arguments,
            str,
        ):
            try:
                arguments = json.loads(
                    arguments
                )
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"{self.name} ha restituito argomenti "
                    "tool non validi."
                ) from error

        if not isinstance(
            arguments,
            dict,
        ):
            raise RuntimeError(
                f"{self.name} ha restituito argomenti tool "
                "che non sono un oggetto JSON."
            )

        call_id = call.get(
            "id"
        )

        if (
            call_id is not None
            and not isinstance(
                call_id,
                str,
            )
        ):
            call_id = None

        return json.dumps(
            {
                "type": "tool_call",
                "content": None,
                "name": name,
                "arguments": arguments,
                "call_id": call_id,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _extract_content_blocks(
        blocks: list[Any],
    ) -> str:

        parts: list[str] = []

        for block in blocks:
            if not isinstance(
                block,
                dict,
            ):
                continue

            text = block.get(
                "text"
            )

            if isinstance(
                text,
                str,
            ):
                parts.append(
                    text
                )

        return "".join(
            parts
        )

    @staticmethod
    def _normalize_usage(
        usage: dict[str, Any],
    ) -> dict[str, int]:

        input_tokens = (
            usage.get("prompt_tokens")
            if usage.get("prompt_tokens") is not None
            else usage.get("input_tokens")
        )

        output_tokens = (
            usage.get("completion_tokens")
            if usage.get("completion_tokens") is not None
            else usage.get("output_tokens")
        )

        total_tokens = usage.get(
            "total_tokens"
        )

        result: dict[str, int] = {}

        if isinstance(
            input_tokens,
            (int, float),
        ):
            result["input_tokens"] = int(
                input_tokens
            )

        if isinstance(
            output_tokens,
            (int, float),
        ):
            result["output_tokens"] = int(
                output_tokens
            )

        if isinstance(
            total_tokens,
            (int, float),
        ):
            result["total_tokens"] = int(
                total_tokens
            )

        return result
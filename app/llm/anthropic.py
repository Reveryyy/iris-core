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


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        timeout: float = 180.0,
    ):
        self.name = "claude"

        api_key = os.getenv(
            "ANTHROPIC_API_KEY"
        )

        if not api_key:
            raise RuntimeError(
                "La variabile ANTHROPIC_API_KEY non è configurata."
            )

        self.api_key = api_key

        self.model = (
            model
            or "claude-sonnet-5"
        )

        self.timeout = timeout

        self.context_window = None

        self.last_usage: dict[str, int] | None = None

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 512,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:

        self.last_usage = None

        system_parts: list[str] = []
        api_messages: list[dict[str, Any]] = []

        for message in messages:
            role = message.get(
                "role"
            )

            content = message.get(
                "content",
                "",
            )

            if role == "system":
                if isinstance(
                    content,
                    str,
                ):
                    system_parts.append(
                        content
                    )

                continue

            if role not in {
                "user",
                "assistant",
            }:
                continue

            api_messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }

        if system_parts:
            payload["system"] = "\n\n".join(
                system_parts
            )

        if temperature is not None:
            payload["temperature"] = temperature

        if tools:
            payload["tools"] = tools

        if response_format is not None:
            schema = response_format.get(
                "schema"
            )

            if schema is not None:
                payload["output_config"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": schema,
                    }
                }

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
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
                "Claude ha restituito una risposta non JSON."
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

        content_blocks = data.get(
            "content"
        )

        if not isinstance(
            content_blocks,
            list,
        ):
            raise RuntimeError(
                "Claude non ha restituito content valido."
            )

        for block in content_blocks:
            if not isinstance(
                block,
                dict,
            ):
                continue

            if block.get(
                "type"
            ) != "tool_use":
                continue

            name = block.get(
                "name"
            )

            arguments = block.get(
                "input",
                {},
            )

            if not isinstance(
                name,
                str,
            ):
                raise RuntimeError(
                    "Claude ha restituito un tool non valido."
                )

            if not isinstance(
                arguments,
                dict,
            ):
                raise RuntimeError(
                    "Claude ha restituito argomenti tool non validi."
                )

            return json.dumps(
                {
                    "type": "tool_call",
                    "content": None,
                    "name": name,
                    "arguments": arguments,
                    "call_id": block.get(
                        "id"
                    ),
                },
                ensure_ascii=False,
            )

        text_parts: list[str] = []

        for block in content_blocks:
            if not isinstance(
                block,
                dict,
            ):
                continue

            if block.get(
                "type"
            ) != "text":
                continue

            text = block.get(
                "text"
            )

            if isinstance(
                text,
                str,
            ):
                text_parts.append(
                    text
                )

        return json.dumps(
            {
                "type": "final",
                "content": "".join(
                    text_parts
                ),
                "name": None,
                "arguments": {},
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _normalize_usage(
        usage: dict[str, Any],
    ) -> dict[str, int]:

        input_tokens = usage.get(
            "input_tokens"
        )

        output_tokens = usage.get(
            "output_tokens"
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

        if result:
            result["total_tokens"] = (
                result.get(
                    "input_tokens",
                    0,
                )
                + result.get(
                    "output_tokens",
                    0,
                )
            )

        return result
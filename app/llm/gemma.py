import json
from typing import Any

import requests

from app.llm.provider import LLMProvider


class GemmaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
    ):
        self.name = "gemma"
        self.model = "gemma-4-E2B_q4_0-it.gguf"

        self.base_url = base_url.rstrip("/")

        self.context_window = 4096

        self.last_usage: dict[str, int] | None = None

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 512,
        temperature: float = 1.0,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:

        self.last_usage = None

        fast_structured_request = (
            response_format is not None
            or max_tokens <= 256
        )

        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.90,
            "top_k": 40,
            "chat_template_kwargs": {
                "enable_thinking": not fast_structured_request,
            },
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if response_format is not None:
            payload["response_format"] = response_format

        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=180,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise RuntimeError(
                "llama-server ha rifiutato la richiesta "
                f"({response.status_code}): {response.text}"
            ) from error

        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(
                "llama-server ha restituito una risposta "
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
            raise ValueError(
                "llama-server non ha restituito alcuna scelta."
            )

        message = choices[0].get(
            "message"
        )

        if not isinstance(
            message,
            dict,
        ):
            raise ValueError(
                "llama-server ha restituito un messaggio non valido."
            )

        tool_calls = message.get(
            "tool_calls"
        )

        if tool_calls:
            if not isinstance(
                tool_calls,
                list,
            ):
                raise ValueError(
                    "Gemma ha restituito tool_calls non validi."
                )

            call = tool_calls[0]

            if not isinstance(
                call,
                dict,
            ):
                raise ValueError(
                    "Gemma ha restituito una tool call non valida."
                )

            function = call.get(
                "function"
            )

            if not isinstance(
                function,
                dict,
            ):
                raise ValueError(
                    "Gemma ha restituito una funzione tool non valida."
                )

            name = function.get(
                "name"
            )

            if not isinstance(
                name,
                str,
            ) or not name.strip():
                raise ValueError(
                    "Gemma ha restituito un nome tool non valido."
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
                    raise ValueError(
                        "Gemma ha restituito argomenti "
                        "tool non validi."
                    ) from error

            if not isinstance(
                arguments,
                dict,
            ):
                raise ValueError(
                    "Gli argomenti del tool devono essere "
                    "un oggetto JSON."
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
                raise ValueError(
                    "Gemma ha restituito un call_id non valido."
                )

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

        content = message.get(
            "content"
        )

        if content is None:
            content = ""

        if not isinstance(
            content,
            str,
        ):
            raise ValueError(
                "Gemma ha restituito un contenuto finale non valido."
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

    @staticmethod
    def _normalize_usage(
        usage: dict[str, Any],
    ) -> dict[str, int]:

        input_tokens = usage.get(
            "prompt_tokens"
        )

        if input_tokens is None:
            input_tokens = usage.get(
                "input_tokens"
            )

        output_tokens = usage.get(
            "completion_tokens"
        )

        if output_tokens is None:
            output_tokens = usage.get(
                "output_tokens"
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
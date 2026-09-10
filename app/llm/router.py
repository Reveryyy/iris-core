from typing import Any

from app.llm.provider import LLMProvider


class LLMRouter:
    def __init__(
        self,
        providers: list[LLMProvider],
    ):
        self.providers = providers

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 512,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        last_error: Exception | None = None

        for provider in self.providers:
            try:
                kwargs: dict[str, Any] = {
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }

                if response_format is not None:
                    kwargs["response_format"] = response_format

                if tools is not None:
                    kwargs["tools"] = tools

                return provider.generate(
                    messages,
                    **kwargs,
                )

            except Exception as error:
                last_error = error

        if last_error is not None:
            raise RuntimeError(
                "Nessun provider LLM disponibile: "
                f"{last_error}"
            ) from last_error

        raise RuntimeError(
            "Nessun provider LLM configurato."
        )
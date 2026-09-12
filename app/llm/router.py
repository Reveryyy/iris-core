from __future__ import annotations

from time import perf_counter
from typing import Any

from app.llm.errors import (
    LLMErrorCategory,
    LLMProviderError,
    classify_exception,
)
from app.llm.provider import LLMProvider
from app.ui.events import IRISEventBus


class LLMRouter:
    """
    Router multi-provider di IRIS.

    Gestisce:
    - routing automatico;
    - provider forzato;
    - fallback;
    - telemetria;
    - stato dei provider.
    """

    DEFAULT_TASK_ROUTES = {
        "coding": [
            "claude",
            "openai",
            "gemini",
            "groq",
            "cerebras",
            "mistral",
            "openrouter",
            "fireworks",
            "siliconflow",
            "gemma",
        ],
        "agent": [
            "gemini",
            "groq",
            "cerebras",
            "mistral",
            "openrouter",
            "fireworks",
            "siliconflow",
            "gemma",
        ],
        "general": [
            "gemini",
            "groq",
            "mistral",
            "cerebras",
            "openrouter",
            "cohere",
            "fireworks",
            "siliconflow",
            "gemma",
        ],
        "fast": [
            "groq",
            "cerebras",
            "gemini",
            "openrouter",
            "mistral",
            "fireworks",
            "siliconflow",
            "gemma",
        ],
        "memory": [
            "gemini",
            "groq",
            "mistral",
            "cohere",
            "cerebras",
            "openrouter",
            "gemma",
        ],
        "offline": [
            "gemma",
        ],
    }

    FALLBACK_CATEGORIES = {
        LLMErrorCategory.AUTH_INVALID,
        LLMErrorCategory.AUTH_EXPIRED,
        LLMErrorCategory.PERMISSION_ERROR,
        LLMErrorCategory.NO_CREDITS,
        LLMErrorCategory.BILLING_LIMIT,
        LLMErrorCategory.USAGE_LIMIT,
        LLMErrorCategory.RATE_LIMITED,
        LLMErrorCategory.CAPACITY_LIMITED,
        LLMErrorCategory.MODEL_UNAVAILABLE,
        LLMErrorCategory.SERVER_ERROR,
        LLMErrorCategory.TIMEOUT,
        LLMErrorCategory.NETWORK_ERROR,
        LLMErrorCategory.REQUEST_CANCELLED,
        LLMErrorCategory.UNSUPPORTED_FEATURE,
        LLMErrorCategory.UNKNOWN,
    }

    NON_FALLBACK_CATEGORIES = {
        LLMErrorCategory.INVALID_REQUEST,
        LLMErrorCategory.REQUEST_TOO_LARGE,
        LLMErrorCategory.CONTENT_BLOCKED,
    }

    def __init__(
        self,
        providers: list[LLMProvider],
        task_routes: dict[str, list[str]] | None = None,
        event_bus: IRISEventBus | None = None,
    ):
        self.providers = providers

        self.task_routes = (
            task_routes
            or {
                key: list(value)
                for key, value
                in self.DEFAULT_TASK_ROUTES.items()
            }
        )

        self.event_bus = (
            event_bus
            or IRISEventBus()
        )

        self._providers_by_name: dict[
            str,
            LLMProvider,
        ] = {}

        self._disabled_providers: dict[
            str,
            LLMProviderError,
        ] = {}

        self._forced_provider: str | None = None

        for provider in providers:
            name = self._provider_name(
                provider
            )

            self._providers_by_name[
                name
            ] = provider

    @property
    def forced_provider(
        self,
    ) -> str | None:
        return self._forced_provider

    def set_forced_provider(
        self,
        provider_name: str,
    ) -> None:
        normalized = (
            provider_name.strip().lower()
        )

        if normalized not in self._providers_by_name:
            raise ValueError(
                "Provider non disponibile: "
                f"{provider_name}"
            )

        self._forced_provider = normalized

    def clear_forced_provider(
        self,
    ) -> None:
        self._forced_provider = None

    def get_provider(
        self,
        provider_name: str,
    ) -> LLMProvider:
        normalized = (
            provider_name.strip().lower()
        )

        provider = self._providers_by_name.get(
            normalized
        )

        if provider is None:
            raise ValueError(
                "Provider non trovato: "
                f"{provider_name}"
            )

        return provider

    def set_provider_model(
        self,
        provider_name: str,
        model: str,
    ) -> None:
        model = model.strip()

        if not model:
            raise ValueError(
                "Il modello non può essere vuoto."
            )

        provider = self.get_provider(
            provider_name
        )

        if not hasattr(
            provider,
            "model",
        ):
            raise ValueError(
                f"Il provider {provider_name} "
                "non supporta la selezione runtime del modello."
            )

        setattr(
            provider,
            "model",
            model,
        )

    def current_provider_name(
        self,
    ) -> str | None:
        return self._forced_provider

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 512,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        task: str = "general",
    ) -> str:

        ordered_providers = (
            self._get_provider_order(
                task
            )
        )

        last_error: LLMProviderError | None = None

        for index, provider in enumerate(
            ordered_providers
        ):
            provider_name = self._provider_name(
                provider
            )

            disabled_error = (
                self._disabled_providers.get(
                    provider_name
                )
            )

            if disabled_error is not None:
                last_error = disabled_error

                self.event_bus.emit(
                    "provider.disabled",
                    provider=provider_name,
                    category=disabled_error.category.value,
                )

                continue

            model = str(
                getattr(
                    provider,
                    "model",
                    provider.__class__.__name__,
                )
            )

            context_window = getattr(
                provider,
                "context_window",
                None,
            )

            self.event_bus.emit(
                "llm.started",
                provider=provider_name,
                model=model,
                task=task,
                context_window=context_window,
                max_tokens=max_tokens,
            )

            started = perf_counter()

            try:
                kwargs: dict[str, Any] = {
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }

                if response_format is not None:
                    kwargs["response_format"] = (
                        response_format
                    )

                if tools is not None:
                    kwargs["tools"] = tools

                result = provider.generate(
                    messages,
                    **kwargs,
                )

                elapsed = (
                    perf_counter() - started
                )

                usage = getattr(
                    provider,
                    "last_usage",
                    None,
                )

                self.event_bus.emit(
                    "llm.completed",
                    provider=provider_name,
                    model=model,
                    task=task,
                    usage=usage,
                    latency_seconds=elapsed,
                )

                return result

            except Exception as error:
                elapsed = (
                    perf_counter() - started
                )

                classified = classify_exception(
                    provider=provider_name,
                    error=error,
                )

                last_error = classified

                self.event_bus.emit(
                    "llm.error",
                    provider=provider_name,
                    model=model,
                    task=task,
                    category=classified.category.value,
                    message=str(classified),
                    latency_seconds=elapsed,
                )

                if classified.disable_provider:
                    self._disabled_providers[
                        provider_name
                    ] = classified

                    self.event_bus.emit(
                        "provider.disabled",
                        provider=provider_name,
                        category=classified.category.value,
                    )

                forced = (
                    self._forced_provider is not None
                )

                if forced:
                    raise classified from error

                if (
                    classified.category
                    in self.NON_FALLBACK_CATEGORIES
                ):
                    raise classified from error

                if (
                    classified.category
                    not in self.FALLBACK_CATEGORIES
                ):
                    raise classified from error

                next_provider_name = (
                    self._next_provider_name(
                        ordered_providers,
                        index,
                    )
                )

                if next_provider_name is not None:
                    self.event_bus.emit(
                        "router.fallback",
                        provider=provider_name,
                        category=classified.category.value,
                        next_provider=next_provider_name,
                    )

                continue

        if last_error is not None:
            raise RuntimeError(
                "Nessun provider LLM disponibile. "
                f"Ultimo errore: {last_error}"
            ) from last_error

        raise RuntimeError(
            "Nessun provider LLM configurato."
        )

    def enable_provider(
        self,
        provider_name: str,
    ) -> None:
        self._disabled_providers.pop(
            provider_name.strip().lower(),
            None,
        )

    def disable_provider(
        self,
        provider_name: str,
        error: LLMProviderError,
    ) -> None:
        self._disabled_providers[
            provider_name.strip().lower()
        ] = error

    def provider_status(
        self,
    ) -> dict[str, str]:

        status: dict[str, str] = {}

        for provider in self.providers:
            name = self._provider_name(
                provider
            )

            error = self._disabled_providers.get(
                name
            )

            if error is None:
                status[name] = "available"
            else:
                status[name] = (
                    error.category.value
                )

        return status

    def _get_provider_order(
        self,
        task: str,
    ) -> list[LLMProvider]:

        if self._forced_provider is not None:
            forced = self._providers_by_name.get(
                self._forced_provider
            )

            if forced is None:
                raise RuntimeError(
                    "Il provider forzato non è più disponibile: "
                    f"{self._forced_provider}"
                )

            return [
                forced
            ]

        normalized_task = (
            task.strip().lower()
            if isinstance(
                task,
                str,
            )
            else "general"
        )

        preferred_names = self.task_routes.get(
            normalized_task
        )

        if preferred_names is None:
            preferred_names = (
                self.task_routes.get(
                    "general",
                    [],
                )
            )

        ordered: list[LLMProvider] = []
        seen: set[str] = set()

        for name in preferred_names:
            provider = (
                self._providers_by_name.get(
                    name
                )
            )

            if provider is None:
                continue

            if name in seen:
                continue

            seen.add(
                name
            )

            ordered.append(
                provider
            )

        for provider in self.providers:
            name = self._provider_name(
                provider
            )

            if name in seen:
                continue

            seen.add(
                name
            )

            ordered.append(
                provider
            )

        return ordered

    @staticmethod
    def _next_provider_name(
        providers: list[LLMProvider],
        index: int,
    ) -> str | None:

        next_index = index + 1

        if next_index >= len(providers):
            return None

        provider = providers[
            next_index
        ]

        name = getattr(
            provider,
            "name",
            provider.__class__.__name__,
        )

        return str(
            name
        ).lower()

    @staticmethod
    def _provider_name(
        provider: LLMProvider,
    ) -> str:

        name = getattr(
            provider,
            "name",
            None,
        )

        if isinstance(
            name,
            str,
        ) and name.strip():
            return name.strip().lower()

        return (
            provider.__class__.__name__
            .strip()
            .lower()
        )
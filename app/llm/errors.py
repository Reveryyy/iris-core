from __future__ import annotations

import json
from enum import Enum
from typing import Any


class LLMErrorCategory(str, Enum):
    AUTH_INVALID = "auth_invalid"
    AUTH_EXPIRED = "auth_expired"
    PERMISSION_ERROR = "permission_error"

    NO_CREDITS = "no_credits"
    BILLING_LIMIT = "billing_limit"
    USAGE_LIMIT = "usage_limit"

    RATE_LIMITED = "rate_limited"
    CAPACITY_LIMITED = "capacity_limited"

    MODEL_UNAVAILABLE = "model_unavailable"
    UNSUPPORTED_FEATURE = "unsupported_feature"

    INVALID_REQUEST = "invalid_request"
    REQUEST_TOO_LARGE = "request_too_large"
    CONTENT_BLOCKED = "content_blocked"

    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"

    REQUEST_CANCELLED = "request_cancelled"
    UNKNOWN = "unknown"


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        category: LLMErrorCategory,
        message: str,
        status_code: int | None = None,
        provider_code: str | None = None,
        provider_type: str | None = None,
        retryable: bool = False,
        disable_provider: bool = False,
        raw_error: Any = None,
    ) -> None:
        super().__init__(message)

        self.provider = provider
        self.category = category
        self.message = message
        self.status_code = status_code
        self.provider_code = provider_code
        self.provider_type = provider_type
        self.retryable = retryable
        self.disable_provider = disable_provider
        self.raw_error = raw_error

    def __str__(self) -> str:
        details = [
            self.provider,
            self.category.value,
        ]

        if self.status_code is not None:
            details.append(
                f"HTTP {self.status_code}"
            )

        if self.provider_code:
            details.append(
                f"code={self.provider_code}"
            )

        return (
            "["
            + " | ".join(details)
            + "] "
            + self.message
        )


def classify_http_error(
    *,
    provider: str,
    status_code: int,
    payload: Any = None,
    response_text: str = "",
) -> LLMProviderError:
    """
    Classifica un errore HTTP usando regole specifiche
    del provider.

    Il payload originale viene mantenuto nell'eccezione.
    """

    provider_name = provider.strip().lower()

    error_data = _extract_error_object(
        payload
    )

    message = _extract_message(
        error_data,
        response_text,
    )

    provider_code = _extract_code(
        error_data
    )

    error_type = _extract_type(
        error_data
    )

    combined = " ".join(
        part
        for part in (
            provider_code or "",
            error_type or "",
            message,
        )
        if part
    ).lower()

    # ---------------------------------------------------------
    # OPENAI
    # ---------------------------------------------------------

    if provider_name == "openai":
        category = _classify_openai(
            status_code=status_code,
            provider_code=provider_code,
            error_type=error_type,
            combined=combined,
        )

        return _make_error(
            provider=provider,
            category=category,
            message=message,
            status_code=status_code,
            provider_code=provider_code,
            payload=payload,
        )

    # ---------------------------------------------------------
    # GROQ
    # ---------------------------------------------------------

    if provider_name == "groq":
        category = _classify_groq(
            status_code=status_code,
            combined=combined,
        )

        return _make_error(
            provider=provider,
            category=category,
            message=message,
            status_code=status_code,
            provider_code=provider_code,
            payload=payload,
        )

    # ---------------------------------------------------------
    # MISTRAL
    # ---------------------------------------------------------

    if provider_name == "mistral":
        category = _classify_mistral(
            status_code=status_code,
            combined=combined,
        )

        return _make_error(
            provider=provider,
            category=category,
            message=message,
            status_code=status_code,
            provider_code=provider_code,
            payload=payload,
        )

    # ---------------------------------------------------------
    # COHERE
    # ---------------------------------------------------------

    if provider_name == "cohere":
        category = _classify_cohere(
            status_code=status_code,
            combined=combined,
        )

        return _make_error(
            provider=provider,
            category=category,
            message=message,
            status_code=status_code,
            provider_code=provider_code,
            payload=payload,
        )

    # ---------------------------------------------------------
    # GENERIC OPENAI-COMPATIBLE PROVIDERS
    # ---------------------------------------------------------

    category = _classify_generic(
        status_code=status_code,
        combined=combined,
    )

    return _make_error(
        provider=provider,
        category=category,
        message=message,
        status_code=status_code,
        provider_code=provider_code,
        payload=payload,
    )


def classify_exception(
    *,
    provider: str,
    error: Exception,
) -> LLMProviderError:
    """
    Converte timeout/network error in categorie IRIS.
    Gli errori non HTTP vengono classificati qui.
    """

    import requests

    if isinstance(
        error,
        LLMProviderError,
    ):
        return error

    if isinstance(
        error,
        requests.Timeout,
    ):
        return LLMProviderError(
            provider=provider,
            category=LLMErrorCategory.TIMEOUT,
            message=str(error),
            retryable=True,
            disable_provider=False,
            raw_error=error,
        )

    if isinstance(
        error,
        requests.ConnectionError,
    ):
        return LLMProviderError(
            provider=provider,
            category=LLMErrorCategory.NETWORK_ERROR,
            message=str(error),
            retryable=True,
            disable_provider=False,
            raw_error=error,
        )

    if isinstance(
        error,
        (ValueError, TypeError),
    ):
        return LLMProviderError(
            provider=provider,
            category=LLMErrorCategory.INVALID_REQUEST,
            message=str(error),
            retryable=False,
            disable_provider=False,
            raw_error=error,
        )

    return LLMProviderError(
        provider=provider,
        category=LLMErrorCategory.UNKNOWN,
        message=str(error),
        retryable=False,
        disable_provider=False,
        raw_error=error,
    )


def _classify_openai(
    *,
    status_code: int,
    provider_code: str | None,
    error_type: str | None,
    combined: str,
) -> LLMErrorCategory:

    code = (
        provider_code or ""
    ).lower()

    if code == "credit_balance_exhausted":
        return LLMErrorCategory.NO_CREDITS

    if code == "organization_usage_limit_exceeded":
        return LLMErrorCategory.USAGE_LIMIT

    if code == "organization_spend_limit_exceeded":
        return LLMErrorCategory.BILLING_LIMIT

    if code == "project_spend_limit_exceeded":
        return LLMErrorCategory.BILLING_LIMIT

    if (
        "insufficient_quota" in combined
        or "quota" in combined
    ):
        return LLMErrorCategory.NO_CREDITS

    return _classify_generic(
        status_code=status_code,
        combined=combined,
    )


def _classify_groq(
    *,
    status_code: int,
    combined: str,
) -> LLMErrorCategory:

    if status_code == 498:
        return LLMErrorCategory.CAPACITY_LIMITED

    if status_code == 499:
        return LLMErrorCategory.REQUEST_CANCELLED

    if status_code == 413:
        return LLMErrorCategory.REQUEST_TOO_LARGE

    if status_code == 422:
        return LLMErrorCategory.INVALID_REQUEST

    return _classify_generic(
        status_code=status_code,
        combined=combined,
    )


def _classify_mistral(
    *,
    status_code: int,
    combined: str,
) -> LLMErrorCategory:

    if status_code == 402:
        return LLMErrorCategory.BILLING_LIMIT

    if status_code == 422:
        return LLMErrorCategory.INVALID_REQUEST

    return _classify_generic(
        status_code=status_code,
        combined=combined,
    )


def _classify_cohere(
    *,
    status_code: int,
    combined: str,
) -> LLMErrorCategory:

    if status_code == 402:
        return LLMErrorCategory.BILLING_LIMIT

    if status_code == 401:
        if (
            "expired" in combined
            or "expire" in combined
        ):
            return LLMErrorCategory.AUTH_EXPIRED

        return LLMErrorCategory.AUTH_INVALID

    if status_code == 499:
        return LLMErrorCategory.REQUEST_CANCELLED

    return _classify_generic(
        status_code=status_code,
        combined=combined,
    )


def _classify_generic(
    *,
    status_code: int,
    combined: str,
) -> LLMErrorCategory:

    if status_code == 401:
        if (
            "expired" in combined
            or "expired key" in combined
        ):
            return LLMErrorCategory.AUTH_EXPIRED

        return LLMErrorCategory.AUTH_INVALID

    if status_code == 403:
        return LLMErrorCategory.PERMISSION_ERROR

    if status_code == 404:
        if (
            "model" in combined
            or "model not found" in combined
            or "unknown_model" in combined
        ):
            return LLMErrorCategory.MODEL_UNAVAILABLE

        return LLMErrorCategory.INVALID_REQUEST

    if status_code == 402:
        return LLMErrorCategory.BILLING_LIMIT

    if status_code == 413:
        return LLMErrorCategory.REQUEST_TOO_LARGE

    if status_code == 422:
        return LLMErrorCategory.INVALID_REQUEST

    if status_code == 429:
        return LLMErrorCategory.RATE_LIMITED

    if 500 <= status_code <= 599:
        return LLMErrorCategory.SERVER_ERROR

    if (
        "content policy" in combined
        or "content blocked" in combined
        or "safety" in combined
        or "blocked" in combined
    ):
        return LLMErrorCategory.CONTENT_BLOCKED

    if (
        "unsupported" in combined
        or "not supported" in combined
    ):
        return LLMErrorCategory.UNSUPPORTED_FEATURE

    return LLMErrorCategory.UNKNOWN


def _make_error(
    *,
    provider: str,
    category: LLMErrorCategory,
    message: str,
    status_code: int | None,
    provider_code: str | None,
    payload: Any,
) -> LLMProviderError:

    retryable_categories = {
        LLMErrorCategory.RATE_LIMITED,
        LLMErrorCategory.CAPACITY_LIMITED,
        LLMErrorCategory.SERVER_ERROR,
        LLMErrorCategory.TIMEOUT,
        LLMErrorCategory.NETWORK_ERROR,
    }

    disable_categories = {
        LLMErrorCategory.AUTH_INVALID,
        LLMErrorCategory.AUTH_EXPIRED,
        LLMErrorCategory.NO_CREDITS,
        LLMErrorCategory.BILLING_LIMIT,
        LLMErrorCategory.USAGE_LIMIT,
    }

    return LLMProviderError(
        provider=provider,
        category=category,
        message=message,
        status_code=status_code,
        provider_code=provider_code,
        retryable=category in retryable_categories,
        disable_provider=category in disable_categories,
        raw_error=payload,
    )


def _extract_error_object(
    payload: Any,
) -> dict[str, Any]:

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    error = payload.get(
        "error"
    )

    if isinstance(
        error,
        dict,
    ):
        return error

    if isinstance(
        error,
        str,
    ):
        return {
            "message": error,
        }

    return payload


def _extract_message(
    error_data: dict[str, Any],
    response_text: str,
) -> str:

    for key in (
        "message",
        "detail",
        "error",
    ):
        value = error_data.get(
            key
        )

        if isinstance(
            value,
            str,
        ) and value.strip():
            return value.strip()

    text = (
        response_text.strip()
        if isinstance(
            response_text,
            str,
        )
        else ""
    )

    if text:
        return text

    try:
        return json.dumps(
            error_data,
            ensure_ascii=False,
        )
    except (
        TypeError,
        ValueError,
    ):
        return "Errore provider non specificato."


def _extract_code(
    error_data: dict[str, Any],
) -> str | None:

    for key in (
        "code",
        "error_code",
        "status",
    ):
        value = error_data.get(
            key
        )

        if isinstance(
            value,
            str,
        ) and value.strip():
            return value.strip()

    return None


def _extract_type(
    error_data: dict[str, Any],
) -> str | None:

    value = error_data.get(
        "type"
    )

    if isinstance(
        value,
        str,
    ) and value.strip():
        return value.strip()

    return None
from __future__ import annotations

from app.memory.local_embedding import LocalEmbeddingProvider


class FakeModel:
    def __init__(self) -> None:
        self.received_text: str | None = None

    def encode(
        self,
        text: str,
    ):
        self.received_text = text

        class FakeEmbedding:
            def tolist(self) -> list[float]:
                return [
                    0.1,
                    0.2,
                    0.3,
                ]

        return FakeEmbedding()


def test_embed_accepts_normal_unicode() -> None:
    provider = LocalEmbeddingProvider.__new__(
        LocalEmbeddingProvider
    )

    fake_model = FakeModel()
    provider.model = fake_model

    result = provider.embed(
        "àèéìòù € 😀"
    )

    assert result == [
        0.1,
        0.2,
        0.3,
    ]

    assert fake_model.received_text == (
        "àèéìòù € 😀"
    )


def test_normalize_text_converts_surrogate_pair_to_emoji() -> None:
    provider = LocalEmbeddingProvider.__new__(
        LocalEmbeddingProvider
    )

    surrogate_text = (
        "àèéìòù € "
        "\ud83d\ude00"
    )

    normalized = provider._normalize_text(
        surrogate_text
    )

    assert normalized == (
        "àèéìòù € 😀"
    )


def test_normalize_text_replaces_unpaired_surrogate() -> None:
    provider = LocalEmbeddingProvider.__new__(
        LocalEmbeddingProvider
    )

    text = (
        "ciao "
        "\ud83d"
    )

    normalized = provider._normalize_text(
        text
    )

    assert normalized == (
        "ciao �"
    )


def test_embed_normalizes_surrogate_pair_before_tokenizer() -> None:
    provider = LocalEmbeddingProvider.__new__(
        LocalEmbeddingProvider
    )

    fake_model = FakeModel()
    provider.model = fake_model

    result = provider.embed(
        "àèéìòù € \ud83d\ude00"
    )

    assert result == [
        0.1,
        0.2,
        0.3,
    ]

    assert fake_model.received_text == (
        "àèéìòù € 😀"
    )


def test_embed_rejects_non_string_input() -> None:
    provider = LocalEmbeddingProvider.__new__(
        LocalEmbeddingProvider
    )

    fake_model = FakeModel()
    provider.model = fake_model

    try:
        provider.embed(123)  # type: ignore[arg-type]
    except TypeError as error:
        assert (
            str(error)
            == (
                "Il testo da convertire in embedding "
                "deve essere una stringa."
            )
        )
    else:
        raise AssertionError(
            "Era previsto un TypeError."
        )
from __future__ import annotations

from sentence_transformers import SentenceTransformer

from app.memory.embedding import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.model = SentenceTransformer(
            model_name
        )

    def embed(
        self,
        text: str,
    ) -> list[float]:
        if not isinstance(
            text,
            str,
        ):
            raise TypeError(
                "Il testo da convertire in embedding "
                "deve essere una stringa."
            )

        normalized_text = self._normalize_text(
            text
        )

        embedding = self.model.encode(
            normalized_text
        )

        return embedding.tolist()

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:
        """
        Normalizza eventuali surrogate UTF-16 presenti nella stringa.

        Su Windows un input Unicode può arrivare in alcuni casi come
        coppie surrogate invece di un singolo code point Unicode.
        Il tokenizer Hugging Face può rifiutare questi valori.

        Le normali stringhe Unicode, comprese le emoji già rappresentate
        correttamente da Python, non vengono alterate.
        """

        if not text:
            return text

        return (
            text
            .encode(
                "utf-16",
                errors="surrogatepass",
            )
            .decode(
                "utf-16",
                errors="replace",
            )
        )


__all__ = [
    "LocalEmbeddingProvider",
]
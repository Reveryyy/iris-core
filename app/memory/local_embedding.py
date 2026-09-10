from sentence_transformers import SentenceTransformer

from app.memory.embedding import EmbeddingProvider

class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(
            self,
            model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        embedding = self.model.encode(text)

        return embedding.tolist()
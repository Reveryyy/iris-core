from abc import ABC, abstractmethod

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Converte un testo in un vettore numerico."""
        raise NotImplementedError
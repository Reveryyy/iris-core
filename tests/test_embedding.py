from app.memory.local_embedding import LocalEmbeddingProvider


def test_embedding_generation():
    provider = LocalEmbeddingProvider()

    embedding = provider.embed("Il mio nome è Valerio.")

    assert len(embedding) == 384
    assert all(isinstance(value, float) for value in embedding)
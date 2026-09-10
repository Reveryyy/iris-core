from sqlalchemy import select

from app.database import SessionLocal
from app.memory.local_embedding import LocalEmbeddingProvider
from app.memory.manager import MemoryManager
from app.memory.model import Memory


def clear_memories(db):
    db.query(Memory).delete()
    db.commit()


def test_real_embedding_similarity():
    provider = LocalEmbeddingProvider()

    with SessionLocal() as db:
        clear_memories(db)

        manager = MemoryManager(
            db,
            embedding_provider=provider,
        )

        first = manager.store(
            content="Preferisco programmare in Java.",
            memory_type="preference",
            importance=5,
            confidence=0.9,
            source="user",
        )

        result = manager.find_similar(
            "Il linguaggio che preferisco usare per programmare è Java.",
            threshold=0.60,
        )

        assert result is not None

        similar_memory, distance = result

        assert similar_memory.id == first.id
        assert distance < 0.60


def test_real_embedding_distinguishes_unrelated_memory():
    provider = LocalEmbeddingProvider()

    with SessionLocal() as db:
        clear_memories(db)

        manager = MemoryManager(
            db,
            embedding_provider=provider,
        )

        first = manager.store(
            content="Preferisco programmare in Java.",
            memory_type="preference",
            importance=5,
            confidence=0.9,
            source="user",
        )

        result = manager.find_similar(
            "Il mio colore preferito è il blu.",
            threshold=0.60,
        )

        assert result is None
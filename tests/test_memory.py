from app.database import Base, engine, SessionLocal
from app.memory.manager import MemoryManager
from app.memory.model import Memory
from app.memory.local_embedding import LocalEmbeddingProvider


def setup_database():
    Base.metadata.create_all(bind=engine)


def clear_memories():
    with SessionLocal() as db:
        db.query(Memory).delete()
        db.commit()


def test_memory_store_and_get():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        memory = manager.store(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
        )

        assert memory.id is not None

        loaded = manager.get(memory.id)

        assert loaded is not None
        assert loaded.content == "Il mio nome è Valerio."
        assert loaded.memory_type == "semantic"
        assert loaded.importance == 5


def test_memory_update():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        memory = manager.store(
            content="Mi piace Python.",
            memory_type="preference",
            importance=3,
        )

        updated = manager.update(
            memory.id,
            content="Mi piace molto Python.",
            importance=5,
        )

        assert updated is not None
        assert updated.content == "Mi piace molto Python."
        assert updated.memory_type == "preference"
        assert updated.importance == 5


def test_memory_forget():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        memory = manager.store(
            content="Memoria temporanea.",
            memory_type="episodic",
        )

        deleted = manager.forget(memory.id)

        assert deleted is True
        assert manager.get(memory.id) is None


def test_memory_not_found():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        assert manager.get(999999) is None
        assert manager.update(999999, content="Test") is None
        assert manager.forget(999999) is False

def test_memory_persists_between_sessions():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        memory = manager.store(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
        )

        memory_id = memory.id

    with SessionLocal() as db:
        manager = MemoryManager(db)

        loaded = manager.get(memory_id)

        assert loaded is not None
        assert loaded.content == "Il mio nome è Valerio."
        assert loaded.memory_type == "semantic"
        assert loaded.importance == 5

def test_memory_search():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        manager.store(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
        )

        manager.store(
            content="Mi piace programmare in Python.",
            memory_type="preference",
            importance=3,
        )

        results = manager.search("Valerio")

        assert len(results) == 1
        assert results[0].content == "Il mio nome è Valerio."

class FakeEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        return [0.5] * 384


def test_memory_store_with_embedding():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(
            db,
            embedding_provider=FakeEmbeddingProvider(),
        )

        memory = manager.store(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
        )

        assert memory.embedding is not None
        assert len(memory.embedding) == 384
        assert memory.embedding == [0.5] * 384

def test_memory_semantic_search():
    setup_database()
    clear_memories()

    class FakeEmbeddingProvider:
        def embed(self, text: str) -> list[float]:
            if "python" in text.lower():
                return [1.0, 0.0, 0.0] + [0.0] * 381

            return [0.0, 1.0, 0.0] + [0.0] * 381

    with SessionLocal() as db:
        manager = MemoryManager(
            db,
            embedding_provider=FakeEmbeddingProvider(),
        )

        python_memory = manager.store(
            content="Mi piace programmare in Python.",
            memory_type="preference",
            importance=5,
        )

        manager.store(
            content="Il mio colore preferito è il blu.",
            memory_type="preference",
            importance=3,
        )

        results = manager.search_semantic(
            "Quale linguaggio mi piace usare in Python?"
        )

        assert len(results) == 2

        first_memory, first_score = results[0]

        assert first_memory.id == python_memory.id
        assert first_score >= 0.0

def test_memory_metadata_is_persisted():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        memory = manager.store(
            content="Uso IntelliJ per programmare in Java.",
            memory_type="preference",
            importance=4,
            confidence=0.92,
            source="user",
        )

        loaded = manager.get(memory.id)

        assert loaded is not None
        assert loaded.confidence == 0.92
        assert loaded.source == "user"

def test_memory_store_deduplicates_exact_content():
    setup_database()
    clear_memories()

    with SessionLocal() as db:
        manager = MemoryManager(db)

        first = manager.store(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=3,
            confidence=0.8,
            source="user",
        )

        second = manager.store(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
            confidence=0.95,
            source="user",
        )

        assert first.id == second.id

        memories = db.query(Memory).all()

        assert len(memories) == 1
        assert memories[0].importance == 5
        assert memories[0].confidence == 0.95

def test_memory_update_regenerates_embedding():
    setup_database()
    clear_memories()

    class FakeEmbeddingProvider:
        def embed(self, text: str) -> list[float]:
            if "java" in text.lower():
                return [1.0, 0.0, 0.0] + [0.0] * 381

            return [0.0, 1.0, 0.0] + [0.0] * 381

    with SessionLocal() as db:
        manager = MemoryManager(
            db,
            embedding_provider=FakeEmbeddingProvider(),
        )

        memory = manager.store(
            content="Preferisco Java.",
            memory_type="preference",
            importance=5,
        )

        assert memory.embedding == [1.0, 0.0, 0.0] + [0.0] * 381

        updated = manager.update(
            memory.id,
            content="Preferisco Kotlin.",
        )

        assert updated is not None
        assert updated.content == "Preferisco Kotlin."
        assert updated.embedding == [0.0, 1.0, 0.0] + [0.0] * 381

def test_memory_find_similar():
    setup_database()
    clear_memories()

    class FakeEmbeddingProvider:
        def embed(self, text: str) -> list[float]:
            if "python" in text.lower():
                return [1.0, 0.0, 0.0] + [0.0] * 381

            if "java" in text.lower():
                return [0.0, 1.0, 0.0] + [0.0] * 381

            return [0.9, 0.1, 0.0] + [0.0] * 381

    with SessionLocal() as db:
        manager = MemoryManager(
            db,
            embedding_provider=FakeEmbeddingProvider(),
        )

        python_memory = manager.store(
            content="Mi piace programmare in Python.",
            memory_type="preference",
            importance=5,
        )

        similar = manager.find_similar(
            "Preferisco usare Python.",
            threshold=0.15,
        )

        assert similar is not None

        found_memory, distance = similar

        assert found_memory.id == python_memory.id
        assert distance < 0.15


def test_memory_find_similar_returns_none_when_too_different():
    setup_database()
    clear_memories()

    class FakeEmbeddingProvider:
        def embed(self, text: str) -> list[float]:
            if "python" in text.lower():
                return [1.0, 0.0, 0.0] + [0.0] * 381

            return [0.0, 1.0, 0.0] + [0.0] * 381

    with SessionLocal() as db:
        manager = MemoryManager(
            db,
            embedding_provider=FakeEmbeddingProvider(),
        )

        manager.store(
            content="Mi piace programmare in Python.",
            memory_type="preference",
            importance=5,
        )

        similar = manager.find_similar(
            "Il mio colore preferito è il blu.",
            threshold=0.15,
        )

        assert similar is None

def test_memory_store_deduplicates_semantically_similar_content():
    setup_database()
    clear_memories()

    class FakeEmbeddingProvider:
        def embed(self, text: str) -> list[float]:
            if "java" in text.lower():
                return [1.0, 0.0, 0.0] + [0.0] * 381

            if "python" in text.lower():
                return [0.0, 1.0, 0.0] + [0.0] * 381

            return [0.0, 0.0, 1.0] + [0.0] * 381

    with SessionLocal() as db:
        manager = MemoryManager(
            db,
            embedding_provider=FakeEmbeddingProvider(),
        )

        first = manager.store(
            content="Preferisco programmare in Java.",
            memory_type="preference",
            importance=3,
            confidence=0.8,
            source="user",
        )

        second = manager.store(
            content="Il linguaggio che preferisco è Java.",
            memory_type="preference",
            importance=5,
            confidence=0.95,
            source="user",
        )

        assert first.id == second.id

        memories = db.query(Memory).all()

        assert len(memories) == 1
        assert memories[0].content == "Il linguaggio che preferisco è Java."
        assert memories[0].importance == 5
        assert memories[0].confidence == 0.95

def test_real_embedding_deduplicates_similar_memory():
    provider = LocalEmbeddingProvider()

    with SessionLocal() as db:
        clear_memories()

        manager = MemoryManager(
            db,
            embedding_provider=provider,
        )

        first = manager.store(
            content="Preferisco programmare in Java.",
            memory_type="preference",
            importance=3,
            confidence=0.8,
            source="user",
        )

        second = manager.store(
            content="Il linguaggio che preferisco usare per programmare è Java.",
            memory_type="preference",
            importance=5,
            confidence=0.95,
            source="user",
        )

        assert second.id == first.id

        memories = db.query(Memory).all()

        assert len(memories) == 1
        assert memories[0].content == (
            "Il linguaggio che preferisco usare per programmare è Java."
        )
        assert memories[0].importance == 5
        assert memories[0].confidence == 0.95
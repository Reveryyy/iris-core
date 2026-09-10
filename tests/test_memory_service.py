from app.database import SessionLocal
from app.memory.manager import MemoryManager
from app.memory.model import Memory
from app.memory.service import MemoryService


def clear_memories(db):
    db.query(Memory).delete()
    db.commit()


def create_service(db):
    return MemoryService(
        manager=MemoryManager(db)
    )


def test_memory_service_remember_and_recall():
    with SessionLocal() as db:
        clear_memories(db)

        service = create_service(db)

        memory_id = service.remember(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
        )

        assert memory_id is not None
        assert service.recall(memory_id) == "Il mio nome è Valerio."


def test_memory_service_search():
    with SessionLocal() as db:
        clear_memories(db)

        service = create_service(db)

        service.remember(
            content="Il mio nome è Valerio.",
            memory_type="semantic",
            importance=5,
        )

        service.remember(
            content="Mi piace programmare in Python.",
            memory_type="preference",
            importance=3,
        )

        results = service.search("Valerio")

        assert results == ["Il mio nome è Valerio."]


def test_memory_service_rejects_unimportant_memory():
    with SessionLocal() as db:
        clear_memories(db)

        service = create_service(db)

        memory_id = service.remember(
            content="Ho bevuto un bicchiere d'acqua.",
            memory_type="episodic",
            importance=1,
        )

        assert memory_id is None
        assert service.search("bicchiere") == []

def test_memory_service_update():
    with SessionLocal() as db:
        clear_memories(db)

        service = create_service(db)

        memory_id = service.remember(
            content="Preferisco Java.",
            memory_type="preference",
            importance=3,
            confidence=0.8,
            source="user",
        )

        assert memory_id is not None

        updated = service.update(
            memory_id,
            content="Preferisco Kotlin.",
            importance=5,
            confidence=0.95,
        )

        assert updated is True
        assert service.recall(memory_id) == "Preferisco Kotlin."


def test_memory_service_forget():
    with SessionLocal() as db:
        clear_memories(db)

        service = create_service(db)

        memory_id = service.remember(
            content="Memoria da eliminare.",
            memory_type="episodic",
            importance=4,
        )

        assert memory_id is not None
        assert service.forget(memory_id) is True
        assert service.recall(memory_id) is None
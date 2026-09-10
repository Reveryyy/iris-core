from app.memory.context import ContextBuilder
from app.memory.model import Memory


def test_context_builder():
    memory = Memory(
        id=1,
        content="Il mio nome è Valerio.",
        memory_type="semantic",
        importance=5,
    )

    builder = ContextBuilder()

    context = builder.build_memory_context(
        [
            (memory, 4.8),
        ]
    )

    assert "Memorie pertinenti:" in context
    assert "Il mio nome è Valerio." in context
    assert "importanza: 5" in context
    assert "rilevanza: 4.800" in context
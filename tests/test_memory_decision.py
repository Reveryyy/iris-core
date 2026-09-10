from app.memory.candidate import MemoryCandidate
from app.memory.decision import MemoryDecision


def test_important_and_confident_memory_should_be_stored():
    decision = MemoryDecision()

    candidate = MemoryCandidate(
        content="Il mio nome è Valerio.",
        memory_type="semantic",
        importance=5,
        confidence=0.98,
        source="user",
    )

    assert decision.should_store(candidate) is True


def test_unimportant_memory_should_not_be_stored():
    decision = MemoryDecision()

    candidate = MemoryCandidate(
        content="Ho bevuto un bicchiere d'acqua.",
        memory_type="episodic",
        importance=1,
        confidence=0.99,
        source="user",
    )

    assert decision.should_store(candidate) is False


def test_uncertain_memory_should_not_be_stored():
    decision = MemoryDecision()

    candidate = MemoryCandidate(
        content="Forse preferisco Java.",
        memory_type="preference",
        importance=5,
        confidence=0.4,
        source="inference",
    )

    assert decision.should_store(candidate) is False
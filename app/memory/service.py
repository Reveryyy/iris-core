from app.memory.candidate import MemoryCandidate
from app.memory.decision import MemoryDecision
from app.memory.manager import MemoryManager


class MemoryService:
    def __init__(
            self,
            manager: MemoryManager,
            decision: MemoryDecision | None = None,
    ):
        self.manager = manager
        self.decision = decision or MemoryDecision()

    def remember(
            self,
            content: str,
            memory_type: str,
            importance: int = 1,
            confidence: float = 1.0,
            source: str = "user",
    ) -> int | None:

        candidate = MemoryCandidate(
            content=content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            source=source,
        )

        if not self.decision.should_store(candidate):
            return None

        memory = self.manager.store(
            content=content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            source=source,
        )

        return memory.id

    def recall(self, memory_id: int) -> str | None:
        memory = self.manager.get(memory_id)

        if memory is None:
            return None

        return memory.content

    def search(
            self,
            query: str,
            limit: int = 10,
    ) -> list[str]:

        memories = self.manager.search(
            query=query,
            limit=limit,
        )

        return [
            memory.content
            for memory in memories
        ]

    def search_semantic(
            self,
            query: str,
            limit: int = 5,
    ) -> list[tuple]:

        return self.manager.search_semantic(
            query=query,
            limit=limit,
        )

    def search_by_type(
            self,
            memory_type: str,
    ) -> list[str]:

        memories = self.manager.search_by_type(
            memory_type=memory_type,
        )

        return [
            memory.content
            for memory in memories
        ]

    def update(
            self,
            memory_id: int,
            content: str | None = None,
            memory_type: str | None = None,
            importance: int | None = None,
            confidence: float | None = None,
            source: str | None = None,
    ) -> bool:

        memory = self.manager.update(
            memory_id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            source=source,
        )

        return memory is not None

    def forget(self, memory_id: int) -> bool:
        return self.manager.forget(memory_id)
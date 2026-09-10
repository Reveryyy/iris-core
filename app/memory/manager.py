from sqlalchemy.orm import Session
from sqlalchemy import select

from app.memory.embedding import EmbeddingProvider
from app.memory.model import Memory


class MemoryManager:
    SIMILARITY_DISTANCE_THRESHOLD = 0.45

    def __init__(
            self,
            db: Session,
            embedding_provider: EmbeddingProvider | None = None,
    ):
        self.db = db
        self.embedding_provider = embedding_provider

    def store(
            self,
            content: str,
            memory_type: str,
            importance: int = 1,
            confidence: float = 1.0,
            source: str = "user",
    ) -> Memory:

        existing = self.find_exact(content)

        if existing is None and self.embedding_provider is not None:
            similar = self.find_similar(
                content,
                threshold=self.SIMILARITY_DISTANCE_THRESHOLD,
            )

            if similar is not None:
                existing = similar[0]

        if existing is not None:
            existing.content = content
            existing.memory_type = memory_type
            existing.importance = max(
                existing.importance,
                importance,
            )
            existing.confidence = max(
                existing.confidence,
                confidence,
            )
            existing.source = source

            if self.embedding_provider is not None:
                existing.embedding = (
                    self.embedding_provider.embed(content)
                )

            self.db.commit()
            self.db.refresh(existing)

            return existing

        embedding = None

        if self.embedding_provider is not None:
            embedding = self.embedding_provider.embed(content)

        memory = Memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            source=source,
            embedding=embedding,
        )

        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)

        return memory

    def get(self, memory_id: int) -> Memory | None:
        return self.db.get(Memory, memory_id)

    def update(
            self,
            memory_id: int,
            content: str | None = None,
            memory_type: str | None = None,
            confidence: float | None = None,
            source: str | None = None,
            importance: int | None = None,
    ) -> Memory | None:

        memory = self.get(memory_id)

        if memory is None:
            return None

        if content is not None:
            memory.content = content

            if self.embedding_provider is not None:
                memory.embedding = (
                    self.embedding_provider.embed(content)
                )

        if memory_type is not None:
            memory.memory_type = memory_type

        if confidence is not None:
            memory.confidence = confidence

        if source is not None:
            memory.source = source

        if importance is not None:
            memory.importance = importance

        self.db.commit()
        self.db.refresh(memory)

        return memory

    def search(
            self,
            query: str,
            limit: int = 10,
    ) -> list[Memory]:

        statement = (
            select(Memory)
            .where(Memory.content.ilike(f"%{query}%"))
            .order_by(
                Memory.importance.desc(),
                Memory.created_at.desc(),
            )
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def search_semantic(
            self,
            query: str,
            limit: int = 5,
    ) -> list[tuple[Memory, float]]:

        if self.embedding_provider is None:
            raise RuntimeError(
                "E' necessario un EmbeddingProvider per "
                "la ricerca semantica."
            )

        query_embedding = self.embedding_provider.embed(query)

        distance = Memory.embedding.cosine_distance(
            query_embedding
        )

        statement = (
            select(Memory, distance.label("distance"))
            .where(Memory.embedding.is_not(None))
        )

        results = self.db.execute(statement).all()

        ranked_results = []

        for memory, distance_value in results:
            similarity = 1.0 - float(distance_value)

            score = similarity * memory.importance

            ranked_results.append(
                (memory, score)
            )

        ranked_results.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return ranked_results[:limit]

    def search_by_type(
            self,
            memory_type: str,
    ) -> list[Memory]:

        statement = (
            select(Memory)
            .where(Memory.memory_type == memory_type)
            .order_by(Memory.created_at.desc())
        )

        return list(self.db.scalars(statement).all())

    def forget(self, memory_id: int) -> bool:
        memory = self.get(memory_id)

        if memory is None:
            return False

        self.db.delete(memory)
        self.db.commit()

        return True

    def find_exact(self, content: str) -> Memory | None:
        statement = select(Memory).where(
            Memory.content == content
        )

        return self.db.scalars(statement).first()

    def find_similar(
            self,
            content: str,
            threshold: float | None = None,
    ) -> tuple[Memory, float] | None:

        if self.embedding_provider is None:
            raise RuntimeError(
                "E' necessario un EmbeddingProvider per "
                "trovare memorie simili."
            )

        if threshold is None:
            threshold = self.SIMILARITY_DISTANCE_THRESHOLD

        embedding = self.embedding_provider.embed(content)

        distance = Memory.embedding.cosine_distance(
            embedding
        )

        statement = (
            select(Memory, distance.label("distance"))
            .where(Memory.embedding.is_not(None))
            .order_by(distance)
            .limit(1)
        )

        result = self.db.execute(statement).first()

        if result is None:
            return None

        memory, distance_value = result

        distance_value = float(distance_value)

        if distance_value > threshold:
            return None

        return memory, distance_value
from app.memory.candidate import MemoryCandidate

class MemoryDecision:
    MIN_IMPORTANCE = 3
    MIN_CONFIDENCE = 0.7

    def should_store(self, candidate: MemoryCandidate) -> bool:
        return (
            candidate.importance >= self.MIN_IMPORTANCE
            and candidate.confidence >= self.MIN_CONFIDENCE
        )
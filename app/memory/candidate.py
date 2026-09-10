from dataclasses import dataclass

@dataclass
class MemoryCandidate:
    content: str
    memory_type: str
    importance: int
    confidence: float
    source: str = "user"
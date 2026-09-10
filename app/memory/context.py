from app.memory.model import Memory

class ContextBuilder:
    def build_memory_context(
            self,
            memories: list[tuple[Memory, float]],
    ) -> str:
        if not memories:
            return ""

        lines = ["Memorie pertinenti:"]

        for memory, score in memories:
            lines.append(
                f"- {memory.content} "
                f"(importanza: {memory.importance}, "
                f"rilevanza: {score:.3f})"
            )

        return "\n".join(lines)
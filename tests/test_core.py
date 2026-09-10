from app.core import IRISCore


class FakeRouter:
    def __init__(self):
        self.messages_received = []

    def generate(
            self,
            messages: list[dict[str, str]],
            max_tokens: int = 512,
            temperature: float = 0.2,
    ) -> str:
        self.messages_received.append(messages)
        return "Risposta di test."


class FakeMemoryService:
    def search_semantic(
            self,
            query: str,
            limit: int = 5,
    ):
        return []

    def search_by_type(
            self,
            memory_type: str,
    ):
        return []

    def remember(
            self,
            content: str,
            memory_type: str,
            importance: int = 1,
            confidence: float = 1.0,
            source: str = "user",
    ):
        return None


def remove_system_message(
        messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        message
        for message in messages
        if message["role"] != "system"
    ]


def test_core_invia_il_messaggio_al_router():
    router = FakeRouter()
    memory = FakeMemoryService()

    core = IRISCore(router, memory)

    response = core.chat("Ciao IRIS")

    assert response == "Risposta di test."

    assert remove_system_message(
        router.messages_received[-1]
    ) == [
        {
            "role": "user",
            "content": "Ciao IRIS",
        }
    ]


def test_core_conserva_la_conversazione():
    router = FakeRouter()
    memory = FakeMemoryService()

    core = IRISCore(router, memory)

    core.chat("Mi chiamo Valerio")
    core.chat("Come mi chiamo?")

    assert remove_system_message(
        router.messages_received[-1]
    ) == [
        {
            "role": "user",
            "content": "Mi chiamo Valerio",
        },
        {
            "role": "assistant",
            "content": "Risposta di test.",
        },
        {
            "role": "user",
            "content": "Come mi chiamo?",
        },
    ]
from app.llm.router import LLMRouter


class FakeProvider:
    def __init__(
            self,
            name: str,
            should_fail: bool = False,
    ):
        self.name = name
        self.should_fail = should_fail
        self.calls = 0

    def generate(
            self,
            messages: list[dict[str, str]],
            max_tokens: int = 512,
            temperature: float = 0.2,
    ) -> str:

        self.calls += 1

        if self.should_fail:
            raise RuntimeError(
                f"{self.name} non disponibile"
            )

        return f"Risposta da {self.name}"


def test_router_usa_il_primo_provider_disponibile():
    primo = FakeProvider("Primo")
    secondo = FakeProvider("Secondo")

    router = LLMRouter([primo, secondo])

    result = router.generate(
        [{"role": "user", "content": "Ciao"}]
    )

    assert result == "Risposta da Primo"
    assert primo.calls == 1
    assert secondo.calls == 0


def test_router_fa_fallback_se_il_primo_fallisce():
    primo = FakeProvider(
        "Primo",
        should_fail=True,
    )
    secondo = FakeProvider("Secondo")

    router = LLMRouter([primo, secondo])

    result = router.generate(
        [{"role": "user", "content": "Ciao"}]
    )

    assert result == "Risposta da Secondo"
    assert primo.calls == 1
    assert secondo.calls == 1
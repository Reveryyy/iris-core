
from app.llm.router import LLMRouter
from app.tools import ToolProtocolSchema


class FakeStructuredProvider:
    def __init__(self):
        self.calls = []

    def generate(
            self,
            messages,
            max_tokens=512,
            temperature=0.2,
            response_format=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )

        return '{"type":"final","content":"ok","name":null,"arguments":{}}'


def test_router_passes_structured_response_format():
    provider = FakeStructuredProvider()

    router = LLMRouter(
        providers=[provider]
    )

    response_format = (
        ToolProtocolSchema.response_format()
    )

    result = router.generate(
        [
            {
                "role": "user",
                "content": "Ciao",
            }
        ],
        response_format=response_format,
    )

    assert result.startswith('{"type":"final"')

    assert len(provider.calls) == 1

    call = provider.calls[0]

    assert call["response_format"] == (
        response_format
    )


def test_router_does_not_add_response_format_when_unused():
    provider = FakeStructuredProvider()

    router = LLMRouter(
        providers=[provider]
    )

    router.generate(
        [
            {
                "role": "user",
                "content": "Ciao",
            }
        ]
    )

    assert provider.calls[0]["response_format"] is None


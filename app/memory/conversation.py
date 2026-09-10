import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str | None
    tool_name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class Conversation:
    messages: list[Message] = field(
        default_factory=list
    )

    def add_user_message(
        self,
        content: str,
    ) -> None:
        self.messages.append(
            Message(
                role="user",
                content=content,
            )
        )

    def add_assistant_message(
        self,
        content: str,
    ) -> None:
        self.messages.append(
            Message(
                role="assistant",
                content=content,
            )
        )

    def add_tool_call(
        self,
        content: str | None,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str | None,
    ) -> None:
        self.messages.append(
            Message(
                role="assistant",
                content=content,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                metadata={
                    "arguments": arguments,
                },
            )
        )

    def add_tool_result(
        self,
        content: str,
        tool_name: str,
        tool_call_id: str,
    ) -> None:
        self.messages.append(
            Message(
                role="tool",
                content=content,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
        )

    def get_messages(self) -> list[Message]:
        return self.messages.copy()

    def get_last_message(self) -> Message | None:
        if not self.messages:
            return None

        return self.messages[-1]

    def to_provider_messages(
        self,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []

        index = 0

        while index < len(self.messages):
            message = self.messages[index]

            if (
                message.role == "assistant"
                and message.tool_name is not None
            ):
                arguments = message.metadata.get(
                    "arguments",
                    {},
                )

                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": message.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": message.tool_name,
                                "arguments": json.dumps(
                                    arguments,
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }

                index += 1

                tool_responses: list[dict[str, Any]] = []

                while index < len(self.messages):
                    next_message = self.messages[index]

                    if next_message.role != "tool":
                        break

                    tool_responses.append(
                        {
                            "name": next_message.tool_name,
                            "response": self._decode_tool_result(
                                next_message.content
                            ),
                        }
                    )

                    index += 1

                if tool_responses:
                    assistant_message[
                        "tool_responses"
                    ] = tool_responses

                result.append(
                    assistant_message
                )

                continue

            if message.role == "tool":
                result.append(
                    {
                        "role": "tool",
                        "content": message.content,
                        "tool_call_id": message.tool_call_id,
                        "name": message.tool_name,
                    }
                )

                index += 1
                continue

            result.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

            index += 1

        return result

    @staticmethod
    def _decode_tool_result(
        content: str | None,
    ) -> Any:
        if content is None:
            return ""

        try:
            return json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return content

class ToolProtocolSchema:
    """
    Schema JSON vincolato usato dal modello quando il
    Tool System è attivo.

    La struttura permette due sole modalità:

    final:
        {
            "type": "final",
            "content": "risposta",
            "name": null,
            "arguments": {}
        }

    tool_call:
        {
            "type": "tool_call",
            "content": null,
            "name": "echo",
            "arguments": {
                "text": "Ciao"
            }
        }

    L'uso di campi espliciti e null evita di dipendere
    da oneOf/conditional schemas che potrebbero non essere
    supportati uniformemente dai runtime LLM.
    """

    @classmethod
    def schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "final",
                        "tool_call",
                    ],
                },
                "content": {
                    "type": [
                        "string",
                        "null",
                    ],
                },
                "name": {
                    "type": [
                        "string",
                        "null",
                    ],
                },
                "arguments": {
                    "type": "object",
                },
            },
            "required": [
                "type",
                "content",
                "name",
                "arguments",
            ],
            "additionalProperties": False,
        }

    @classmethod
    def response_format(cls) -> dict:
        return {
            "type": "json_schema",
            "schema": cls.schema(),
        }


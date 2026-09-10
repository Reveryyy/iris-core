import pytest

from app.tools.base import ToolDefinition
from app.tools.protocol import ToolProtocolSchema
from app.tools.validator import ToolSchemaValidator


def make_definition(required=None, additional_properties=False):
    return ToolDefinition(
        name="test_tool",
        description="Test tool.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "count": {"type": "integer"},
                "ratio": {"type": "number"},
                "enabled": {"type": "boolean"},
                "payload": {"type": "object"},
                "items": {"type": "array"},
            },
            "required": required or [],
            "additionalProperties": additional_properties,
        },
        risk_level="low",
        permissions=frozenset(),
    )


def test_protocol_schema_has_required_fields():
    schema = ToolProtocolSchema.schema()

    assert schema["type"] == "object"
    assert set(schema["required"]) == {
        "type",
        "content",
        "name",
        "arguments",
    }
    assert schema["additionalProperties"] is False
    assert schema["properties"]["type"]["enum"] == [
        "final",
        "tool_call",
    ]


def test_protocol_response_format_is_json_schema():
    response_format = ToolProtocolSchema.response_format()

    assert response_format["type"] == "json_schema"
    assert response_format["schema"] == ToolProtocolSchema.schema()


def test_validator_accepts_valid_arguments():
    validator = ToolSchemaValidator()
    definition = make_definition(required=["text"])

    validator.validate(
        definition=definition,
        arguments={"text": "ciao"},
    )


def test_validator_rejects_missing_required_argument():
    validator = ToolSchemaValidator()
    definition = make_definition(required=["text"])

    with pytest.raises(ValueError, match="Argomento obbligatorio mancante: text"):
        validator.validate(
            definition=definition,
            arguments={},
        )


def test_validator_rejects_unknown_argument():
    validator = ToolSchemaValidator()
    definition = make_definition()

    with pytest.raises(ValueError, match="Argomenti non consentiti: unknown"):
        validator.validate(
            definition=definition,
            arguments={"unknown": "x"},
        )


def test_validator_allows_unknown_argument_when_schema_allows_it():
    validator = ToolSchemaValidator()
    definition = make_definition(
        additional_properties=True
    )

    validator.validate(
        definition=definition,
        arguments={"unknown": "x"},
    )


def test_validator_rejects_non_object_arguments():
    validator = ToolSchemaValidator()
    definition = make_definition()

    with pytest.raises(ValueError, match="devono essere un oggetto"):
        validator.validate(
            definition=definition,
            arguments=[],
        )


def test_validator_rejects_invalid_schema_type():
    validator = ToolSchemaValidator()
    definition = ToolDefinition(
        name="bad",
        description="Bad.",
        input_schema={
            "type": "string",
        },
        risk_level="low",
        permissions=frozenset(),
    )

    with pytest.raises(ValueError, match="type='object'"):
        validator.validate(
            definition=definition,
            arguments={},
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("text", 10, "deve essere una stringa"),
        ("count", "10", "deve essere un intero"),
        ("ratio", "1.0", "deve essere un numero"),
        ("enabled", "true", "deve essere booleano"),
        ("payload", "{}", "deve essere un oggetto"),
        ("items", {}, "deve essere una lista"),
    ],
)
def test_validator_rejects_wrong_argument_types(field, value, message):
    validator = ToolSchemaValidator()
    definition = make_definition()

    with pytest.raises(ValueError, match=message):
        validator.validate(
            definition=definition,
            arguments={field: value},
        )


def test_validator_accepts_supported_argument_types():
    validator = ToolSchemaValidator()
    definition = make_definition()

    validator.validate(
        definition=definition,
        arguments={
            "text": "ciao",
            "count": 3,
            "ratio": 1.5,
            "enabled": True,
            "payload": {"a": 1},
            "items": [1, 2, 3],
        },
    )


def test_integer_validator_rejects_boolean():
    validator = ToolSchemaValidator()
    definition = make_definition()

    with pytest.raises(ValueError, match="deve essere un intero"):
        validator.validate(
            definition=definition,
            arguments={"count": True},
        )


def test_number_validator_rejects_boolean():
    validator = ToolSchemaValidator()
    definition = make_definition()

    with pytest.raises(ValueError, match="deve essere un numero"):
        validator.validate(
            definition=definition,
            arguments={"ratio": False},
        )

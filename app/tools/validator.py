from typing import Any

from app.tools.base import ToolDefinition


class ToolSchemaValidator:
    def validate(
            self,
            definition: ToolDefinition,
            arguments: dict[str, Any],
    ) -> None:

        schema = definition.input_schema

        if not isinstance(arguments, dict):
            raise ValueError(
                "Gli argomenti del tool devono essere un oggetto."
            )

        if schema.get("type") != "object":
            raise ValueError(
                "Lo schema del tool deve avere type='object'."
            )

        properties = schema.get(
            "properties",
            {},
        )

        required = schema.get(
            "required",
            [],
        )

        additional_properties = schema.get(
            "additionalProperties",
            True,
        )

        for field in required:
            if field not in arguments:
                raise ValueError(
                    f"Argomento obbligatorio mancante: {field}"
                )

        if not additional_properties:
            unknown = set(arguments) - set(properties)

            if unknown:
                names = ", ".join(
                    sorted(unknown)
                )

                raise ValueError(
                    f"Argomenti non consentiti: {names}"
                )

        for name, value in arguments.items():
            property_schema = properties.get(name)

            if property_schema is None:
                continue

            self._validate_type(
                name=name,
                value=value,
                schema=property_schema,
            )

    def _validate_type(
            self,
            name: str,
            value: Any,
            schema: dict[str, Any],
    ) -> None:

        expected_type = schema.get("type")

        if expected_type == "string":
            if not isinstance(value, str):
                raise ValueError(
                    f"L'argomento '{name}' deve essere una stringa."
                )

        elif expected_type == "integer":
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise ValueError(
                    f"L'argomento '{name}' deve essere un intero."
                )

        elif expected_type == "number":
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
            ):
                raise ValueError(
                    f"L'argomento '{name}' deve essere un numero."
                )

        elif expected_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(
                    f"L'argomento '{name}' deve essere booleano."
                )

        elif expected_type == "object":
            if not isinstance(value, dict):
                raise ValueError(
                    f"L'argomento '{name}' deve essere un oggetto."
                )

        elif expected_type == "array":
            if not isinstance(value, list):
                raise ValueError(
                    f"L'argomento '{name}' deve essere una lista."
                )
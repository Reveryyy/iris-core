
import json

from app.tools.registry import ToolRegistry


class ToolPromptBuilder:
    def build(
            self,
            registry: ToolRegistry,
    ) -> str:

        definitions = registry.definitions()

        if not definitions:
            return ""

        serialized = json.dumps(
            definitions,
            ensure_ascii=False,
            indent=2,
        )

        return (
            "IRIS dispone di un sistema di tool.\n\n"

            "La risposta deve rispettare esclusivamente "
            "il protocollo JSON richiesto dal sistema.\n\n"

            "RISPOSTA FINALE:\n"
            "{\n"
            '  "type": "final",\n'
            '  "content": "la risposta",\n'
            '  "name": null,\n'
            '  "arguments": {}\n'
            "}\n\n"

            "RICHIESTA DI TOOL:\n"
            "{\n"
            '  "type": "tool_call",\n'
            '  "content": null,\n'
            '  "name": "nome_tool",\n'
            '  "arguments": {}\n'
            "}\n\n"

            "REGOLE:\n"
            "- Non dichiarare di aver eseguito un'azione "
            "senza una tool_call valida.\n"
            "- Non inventare tool.\n"
            "- Non inventare argomenti mancanti.\n"
            "- Non riutilizzare automaticamente risultati "
            "precedenti.\n"
            "- Non aggiungere testo fuori dal JSON.\n"
            "- Il sistema verifica tool, schema, permessi "
            "e autorizzazione.\n\n"

            "TOOL DISPONIBILI:\n"
            f"{serialized}"
        )


import json
import re

from app.llm.router import LLMRouter
from app.memory.candidate import MemoryCandidate


class MemoryExtractor:
    CONFIDENCE_THRESHOLD = 0.80

    ALLOWED_MEMORY_TYPES = {
        "semantic",
        "preference",
        "procedural",
        "project",
        "environment",
        "episodic",
    }

    def __init__(self, router: LLMRouter):
        self.router = router

    def extract(self, message: str) -> list[MemoryCandidate]:
        message = message.strip()

        if not message:
            return []

        # I comandi operativi dell'Agent Loop non sono messaggi
        # da analizzare come memoria persistente.
        if message.lower().startswith("/agent"):
            return []

        try:
            response = self.router.generate(
                [
                    {
                        "role": "system",
                        "content": self._build_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": message,
                    },
                ],
                max_tokens=128,
                temperature=0.0,
                response_format={
                    "type": "json_object",
                },
            )

            data = self._parse_json(response)

            if data is None:
                return []

            return self._build_candidates(
                data=data,
                source_message=message,
            )

        except Exception as error:
            print(
                f"[MEMORY ERROR] "
                f"{type(error).__name__}: {error}"
            )
            return []

    def _build_system_prompt(self) -> str:
        return """
Sei il modulo memoria di IRIS.

Analizza esclusivamente il messaggio dell'utente e identifica
informazioni persistenti realmente utili in futuro.

Puoi memorizzare:
- fatti stabili sull'utente;
- preferenze;
- procedure o modalità operative;
- progetti e obiettivi;
- ambiente hardware/software;
- eventi personali utili nel tempo.

Non memorizzare:
- saluti;
- domande;
- richieste normali;
- dettagli temporanei;
- conversazione casuale;
- informazioni inventate o dedotte.

Ogni memoria deve essere atomica: un solo fatto indipendente.

Tipi consentiti:
- semantic
- preference
- procedural
- project
- environment
- episodic

Per ogni memoria restituisci:
- content: frase breve e autonoma;
- memory_type;
- importance: intero da 1 a 5;
- confidence: numero da 0.0 a 1.0;
- evidence: frammento copiato ESATTAMENTE dal messaggio utente.

Non inventare o parafrasare evidence.
Se non c'è nulla da ricordare, restituisci una lista vuota.

Restituisci esclusivamente JSON valido:

{
    "memories": [
        {
            "content": "una singola informazione",
            "memory_type": "preference",
            "importance": 4,
            "confidence": 0.95,
            "evidence": "frammento esatto"
        }
    ]
}
"""

    def _parse_json(self, response: str) -> dict | None:
        response = response.strip()

        response = re.sub(
            r"^```(?:json)?\s*",
            "",
            response,
            flags=re.IGNORECASE,
        )

        response = re.sub(
            r"\s*```$",
            "",
            response,
        )

        try:
            return json.loads(response)

        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}")

            if start == -1 or end == -1 or end <= start:
                return None

            try:
                return json.loads(
                    response[start:end + 1]
                )

            except json.JSONDecodeError:
                return None

    def _build_candidates(
            self,
            data: dict,
            source_message: str,
    ) -> list[MemoryCandidate]:

        memories = data.get("memories")

        if not isinstance(memories, list):
            return []

        candidates = []

        for item in memories:
            if not isinstance(item, dict):
                continue

            content = item.get("content")
            memory_type = item.get("memory_type")
            importance = item.get("importance")
            confidence = item.get("confidence")
            evidence = item.get("evidence")

            if not isinstance(content, str):
                continue

            content = content.strip()

            if not content:
                continue

            if memory_type not in self.ALLOWED_MEMORY_TYPES:
                continue

            if not isinstance(importance, int):
                continue

            if not 1 <= importance <= 5:
                continue

            if not isinstance(confidence, (int, float)):
                continue

            confidence = float(confidence)

            if not 0.0 <= confidence <= 1.0:
                continue

            if confidence < self.CONFIDENCE_THRESHOLD:
                continue

            if not isinstance(evidence, str):
                continue

            evidence = evidence.strip()

            if not evidence:
                continue

            if not self._evidence_is_valid(
                evidence=evidence,
                source_message=source_message,
            ):
                continue

            candidates.append(
                MemoryCandidate(
                    content=content,
                    memory_type=memory_type,
                    importance=importance,
                    confidence=confidence,
                    source="user",
                )
            )

        return candidates

    def _evidence_is_valid(
            self,
            evidence: str,
            source_message: str,
    ) -> bool:

        return evidence in source_message
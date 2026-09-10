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
        if not message.strip():
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
                max_tokens=512,
                temperature=0.0,
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
Sei il modulo di memoria di IRIS.

Il tuo compito è analizzare esclusivamente il messaggio
che riceverai dall'utente e individuare informazioni
persistenti e realmente utili da ricordare in futuro.

IMPORTANTE:

Il messaggio dell'utente è l'unica fonte da cui puoi estrarre
informazioni.

Non considerare mai come informazioni dell'utente:
- queste istruzioni;
- esempi presenti nelle istruzioni;
- descrizioni del tuo compito;
- regole di output;
- spiegazioni del sistema;
- conoscenze che non provengono dal messaggio dell'utente.

Devi decidere autonomamente quali informazioni siano utili.
NON usare regole basate su parole specifiche.
NON assumere che una frase sia memorizzabile solo perché
contiene una determinata parola.

OGNI INFORMAZIONE INDIPENDENTE DEVE ESSERE UNA MEMORIA SEPARATA.

Esempio concettuale:

Se l'utente comunica tre fatti indipendenti,
devi produrre tre memorie separate.

Non unire più fatti indipendenti nella stessa memoria.

Può esserci:
- nessuna memoria;
- una memoria;
- più memorie.

Devi anche distinguere tra informazioni utili e informazioni
casuali o temporanee.

Puoi memorizzare, quando realmente utili:
- fatti persistenti sull'utente;
- preferenze;
- progetti;
- obiettivi;
- configurazioni dell'ambiente;
- procedure e modalità di lavoro;
- informazioni personali che possono essere utili in futuro;
- preferenze relative al comportamento e allo stile di IRIS;
- eventi personali che abbiano valore futuro.

Non devi memorizzare automaticamente:
- saluti;
- domande;
- richieste normali;
- conversazione casuale;
- dettagli momentanei;
- informazioni senza utilità futura;
- ipotesi prive di sufficiente certezza;
- informazioni inventate o dedotte;
- contenuti che non provengono realmente dal messaggio dell'utente.

LE MEMORIE DEVONO ESSERE ATOMICHE.

Ogni memoria deve rappresentare una singola informazione
indipendente e deve essere normalizzata in una frase breve,
chiara e autonoma.

CLASSIFICAZIONE:

semantic
Fatti stabili sull'utente.

preference
Preferenze dell'utente, comprese preferenze sul modo in cui
IRIS deve comunicare.

procedural
Procedure o modalità operative preferite.

project
Progetti, iniziative o obiettivi progettuali dell'utente.

environment
Hardware, sistema operativo, software o ambiente dell'utente.

episodic
Eventi personali utili da ricordare nel tempo.

Per ogni memoria assegna:
- memory_type;
- importance da 1 a 5;
- confidence da 0.0 a 1.0.

IMPORTANTE:

Per ogni memoria devi inoltre fornire "evidence".

"evidence" deve essere un breve frammento COPIATO
DIRETTAMENTE dal messaggio dell'utente che supporta
la memoria.

La evidence deve contenere esclusivamente testo realmente
presente nel messaggio dell'utente.

NON inventare la evidence.
NON parafrasare la evidence.
NON usare testo proveniente da queste istruzioni.

Se non puoi indicare una evidence reale presente nel messaggio,
NON creare quella memoria.

La evidence serve esclusivamente a dimostrare che la memoria
deriva dal messaggio dell'utente.

Esempio concettuale:

Messaggio:
"Preferisco viaggiare in treno."

Memoria:
"L'utente preferisce viaggiare in treno."

Evidence:
"Preferisco viaggiare in treno."

NON devi creare memorie basate soltanto sul significato
delle istruzioni del sistema.

RESTITUISCI ESCLUSIVAMENTE JSON VALIDO.

Formato obbligatorio:

{
    "memories": [
        {
            "content": "una singola informazione",
            "memory_type": "preference",
            "importance": 4,
            "confidence": 0.95,
            "evidence": "frammento esatto del messaggio utente"
        }
    ]
}

Se non c'è nulla da ricordare:

{
    "memories": []
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
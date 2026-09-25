from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4
from dataclasses import dataclass
from typing import Any

from app.agent.decision import AgentDecision
from app.agent.observation import AgentObservation
from app.llm.router import LLMRouter


# ============================================================================
# PLAN MODELS
# ============================================================================

@dataclass(frozen=True)
class AgentPlanStep:
    tool_name: str
    arguments: dict[str, Any]
    description: str
    success_criteria: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.tool_name,
            str,
        ):
            raise TypeError(
                "Il nome del tool del piano deve essere una stringa."
            )

        if not self.tool_name.strip():
            raise ValueError(
                "Il nome del tool del piano non può essere vuoto."
            )

        if not isinstance(
            self.arguments,
            dict,
        ):
            raise TypeError(
                "Gli argomenti del piano devono essere un dizionario."
            )

        if not isinstance(
            self.description,
            str,
        ):
            raise TypeError(
                "La descrizione dello step deve essere una stringa."
            )

        if not self.description.strip():
            raise ValueError(
                "La descrizione dello step non può essere vuota."
            )

        if (
            self.success_criteria is not None
            and not isinstance(
                self.success_criteria,
                str,
            )
        ):
            raise TypeError(
                "I criteri di successo devono essere una stringa oppure None."
            )


@dataclass(frozen=True)
class AgentPlan:
    goal: str
    steps: tuple[AgentPlanStep, ...]
    decision: AgentDecision = AgentDecision.DONE
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.goal,
            str,
        ):
            raise TypeError(
                "L'obiettivo del piano deve essere una stringa."
            )

        if not self.goal.strip():
            raise ValueError(
                "L'obiettivo del piano non può essere vuoto."
            )

        if not isinstance(
            self.steps,
            tuple,
        ):
            raise TypeError(
                "Gli step del piano devono essere una tupla."
            )

        if not self.steps:
            raise ValueError(
                "Il piano deve contenere almeno uno step."
            )

        for step in self.steps:
            if not isinstance(
                step,
                AgentPlanStep,
            ):
                raise TypeError(
                    "Ogni elemento del piano deve essere un AgentPlanStep."
                )

        if not isinstance(
            self.decision,
            AgentDecision,
        ):
            raise TypeError(
                "La decisione del piano deve essere un AgentDecision."
            )

        if (
            self.message is not None
            and not isinstance(
                self.message,
                str,
            )
        ):
            raise TypeError(
                "Il messaggio del piano deve essere una stringa oppure None."
            )


# ============================================================================
# PLANNER
# ============================================================================

class AgentPlanner:
    """
    Genera piani strutturati e li valida contro i contratti reali dei tool.

    Il Planner deve decomporre gli obiettivi composti in azioni atomiche.

    Esempio:

        "apri il blocco note e scrivici ciao"

    deve diventare concettualmente:

        open_application
        focus_window
        type_text

    invece di fermarsi alla prima azione.

    Quando il modello non riesce a produrre un piano valido, il Planner
    dispone inoltre di fallback generici per richieste semplici e
    chiaramente interpretabili. I fallback non contengono nomi di
    applicazioni hardcoded.
    """

    MAX_FORMAT_ATTEMPTS = 3
    MAX_TOOL_VALIDATION_ATTEMPTS = 4

    SINGLE_STEP_MAX_TOKENS = 384
    MULTI_STEP_MAX_TOKENS = 1024

    def __init__(
        self,
        router: LLMRouter,
    ):
        self.router = router

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def plan(
        self,
        goal: str,
        context: str | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
        observations: list[AgentObservation] | None = None,
    ) -> AgentPlan:
        if not isinstance(
            goal,
            str,
        ):
            raise TypeError(
                "L'obiettivo deve essere una stringa."
            )

        if not goal.strip():
            raise ValueError(
                "L'obiettivo non può essere vuoto."
            )

        available_tools = tool_definitions or []

        # Per riferimenti espliciti a una directory già creata e verificata,
        # la risoluzione del percorso deve usare lo stato reale osservato e non
        # lasciare al modello la possibilità di reinterpretare il path.
        reference_file_plan = self._build_file_creation_fallback(
            goal=goal,
            tool_definitions=available_tools,
            context=context,
        )

        if reference_file_plan is not None:
            return reference_file_plan

        reference_copy_plan = self._build_copy_creation_fallback(
            goal=goal,
            tool_definitions=available_tools,
            context=context,
        )

        if reference_copy_plan is not None:
            return reference_copy_plan

        reference_move_plan = self._build_move_creation_fallback(
            goal=goal,
            tool_definitions=available_tools,
            context=context,
        )

        if reference_move_plan is not None:
            return reference_move_plan

        system_content = self._build_system_prompt(
            tool_definitions=available_tools,
            context=context,
            observations=observations,
        )

        base_messages: list[
            dict[str, Any]
        ] = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": goal,
            },
        ]

        is_multi_step = (
            self._looks_like_multi_step_goal(
                goal
            )
        )

        planning_max_tokens = (
            self.MULTI_STEP_MAX_TOKENS
            if is_multi_step
            else self.SINGLE_STEP_MAX_TOKENS
        )

        last_error: Exception | None = None
        format_attempt = 0
        validation_attempt = 0

        messages = list(
            base_messages
        )

        while (
            format_attempt
            < self.MAX_FORMAT_ATTEMPTS
            and validation_attempt
            < self.MAX_TOOL_VALIDATION_ATTEMPTS
        ):
            try:
                response = self.router.generate(
                    messages,
                    max_tokens=planning_max_tokens,
                    temperature=0.0,
                    response_format={
                        "type": "json_object",
                        "schema": self._build_plan_schema(
                            tool_definitions=available_tools,
                            minimum_steps=(
                                2
                                if is_multi_step
                                else 1
                            ),
                        ),
                    },
                    task="agent",
                )

            except Exception as error:
                last_error = error

                format_attempt += 1

                if (
                    format_attempt
                    >= self.MAX_FORMAT_ATTEMPTS
                ):
                    break

                messages = list(
                    base_messages
                )

                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "Si è verificato un errore durante "
                            "la generazione del piano.\n"
                            "Genera nuovamente il piano completo.\n"
                            "Non aggiungere spiegazioni fuori dal JSON."
                        ),
                    },
                )

                continue

            try:
                data = self._decode_response(
                    response
                )

                data = self._normalize_plan(
                    data=data,
                    fallback_goal=goal,
                )

                plan = self._build_plan(
                    goal=goal,
                    data=data,
                )

                validation_error = (
                    self._validate_plan_against_tools(
                        plan,
                        available_tools,
                    )
                )

                if validation_error is None:
                    coverage_error = (
                        self._validate_plan_coverage(
                            goal=goal,
                            plan=plan,
                            tool_definitions=available_tools,
                        )
                    )

                    if coverage_error is None:
                        return plan

                    validation_error = (
                        coverage_error
                    )

                last_error = ValueError(
                    validation_error
                )

                validation_attempt += 1

                if (
                    validation_attempt
                    >= self.MAX_TOOL_VALIDATION_ATTEMPTS
                ):
                    break

                messages = list(
                    base_messages
                )

                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "Il piano precedente NON copriva "
                            "correttamente l'obiettivo.\n\n"
                            "Correggi il piano completo, non solo "
                            "il primo step.\n\n"
                            "Ogni azione distinta richiesta "
                            "dall'utente deve essere rappresentata "
                            "da uno step.\n"
                            "Non accorpare più azioni in un singolo "
                            "tool se i tool disponibili richiedono "
                            "azioni separate.\n"
                            "Mantieni l'ordine logico delle azioni.\n"
                            "Per un obiettivo che richiede aprire "
                            "un'applicazione, usa open_application "
                            "con il nome richiesto anche se non sai "
                            "se l'applicazione sia installata: sarà "
                            "il tool a determinarlo.\n"
                            "Non trasformare una semplice incertezza "
                            "sull'esistenza dell'app in ask_user.\n"
                            "Le azioni già eseguite e verificate "
                            "nelle OSSERVAZIONI fanno parte dello "
                            "stato corrente e non devono essere "
                            "ripetute, salvo richiesta esplicita.\n"
                            "Non dichiarare decision=done finché "
                            "l'intero obiettivo non è coperto.\n\n"
                            f"Errore di validazione: "
                            f"{validation_error}"
                        ),
                    },
                )

                continue

            except (
                TypeError,
                ValueError,
            ) as error:
                last_error = error

                format_attempt += 1

                if (
                    format_attempt
                    >= self.MAX_FORMAT_ATTEMPTS
                ):
                    break

                messages = list(
                    base_messages
                )

                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "La risposta precedente non ha "
                            "rispettato il contratto del Planner.\n"
                            "Genera nuovamente il piano completo.\n"
                            "Scomponi l'obiettivo in tutte le azioni "
                            "necessarie.\n"
                            "Per richieste come 'apri X' devi "
                            "produrre uno step open_application "
                            "con arguments={\"name\":\"X\"}.\n"
                            "Per richieste come 'apri X e poi Y' "
                            "devi produrre due step distinti "
                            "open_application mantenendo l'ordine.\n"
                            "Se X non esiste, non devi saperlo "
                            "durante il planning: sarà il tool "
                            "a verificarlo.\n"
                            "Per 'seleziona tutto' usa "
                            "press_key con key='CTRL+A'.\n"
                            "Per 'cancella il testo' o 'elimina il "
                            "testo', quando non hai prova che il "
                            "contenuto sia già selezionato, usa "
                            "CTRL+A seguito da DELETE.\n"
                            "Per 'scrivi', 'digita' o 'inserisci' "
                            "testo usa type_text.\n"
                            "Non ripetere azioni già eseguite e "
                            "verificate nelle OSSERVAZIONI, salvo "
                            "richiesta esplicita dell'utente.\n"
                            "Restituisci esclusivamente JSON valido, "
                            "senza markdown e senza campi extra."
                        ),
                    },
                )

        fallback_plan = self._build_fallback_plan(
            goal=goal,
            tool_definitions=available_tools,
            context=context,
        )

        if fallback_plan is not None:
            return fallback_plan

        gui_fallback_plan = (
            self._build_gui_control_fallback(
                goal=goal,
                tool_definitions=available_tools,
            )
        )

        if gui_fallback_plan is not None:
            return gui_fallback_plan

        if last_error is not None:
            error_details = (
                f"{type(last_error).__name__}: "
                f"{last_error}"
            )

            cause = last_error.__cause__

            if (
                cause is not None
                and cause is not last_error
            ):
                error_details += (
                    " | causa: "
                    f"{type(cause).__name__}: "
                    f"{cause}"
                )

            raise ValueError(
                "Il planner non ha prodotto un piano eseguibile "
                "dopo i tentativi consentiti. "
                f"Errore: {error_details}"
            ) from last_error

        raise ValueError(
            "Il planner non ha prodotto un piano valido."
        )

    # ========================================================================
    # APPLICATION FALLBACK
    # ========================================================================

    def _build_fallback_plan(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        context: str | None = None,
    ) -> AgentPlan | None:
        """
        Costruisce un piano minimo quando l'LLM non riesce a farlo.

        Il fallback è volutamente ristretto:
        - apertura di una singola applicazione;
        - apertura di più applicazioni in sequenza.

        Non contiene una allowlist di applicazioni e non sostituisce
        il Planner LLM generale.
        """

        directory_plan = self._build_directory_creation_fallback(
            goal=goal,
            tool_definitions=tool_definitions,
            context=context,
        )

        if directory_plan is not None:
            return directory_plan

        file_plan = self._build_file_creation_fallback(
            goal=goal,
            tool_definitions=tool_definitions,
            context=context,
        )

        if file_plan is not None:
            return file_plan

        tool_names = {
            str(
                definition.get(
                    "name"
                )
            )
            for definition in tool_definitions
            if isinstance(
                definition,
                dict,
            )
        }

        if "open_application" not in tool_names:
            return None

        applications = (
            self._extract_application_open_requests(
                goal
            )
        )

        if not applications:
            return None

        steps: list[
            AgentPlanStep
        ] = []

        for application_name in applications:
            steps.append(
                AgentPlanStep(
                    tool_name="open_application",
                    arguments={
                        "name": application_name,
                    },
                    description=(
                        f"Apri l'applicazione "
                        f"'{application_name}'."
                    ),
                    success_criteria=(
                        f"L'applicazione "
                        f"'{application_name}' "
                        "risulta effettivamente "
                        "in esecuzione oppure il "
                        "tool segnala esplicitamente "
                        "che era già aperta."
                    ),
                )
            )

        return AgentPlan(
            goal=goal,
            steps=tuple(
                steps
            ),
            decision=AgentDecision.DONE,
            message=None,
        )

    def _build_copy_creation_fallback(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        context: str | None,
    ) -> AgentPlan | None:
        """Gestisce copie verso una nuova posizione quando la destinazione è generica."""
        if not context:
            return None

        tool_names = {
            str(definition.get("name"))
            for definition in tool_definitions
            if isinstance(definition, dict)
        }

        if "copy_path" not in tool_names:
            return None

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            goal.strip(),
            flags=re.IGNORECASE,
        )
        normalized_lower = normalized.lower()

        if not (
            "copia" in normalized_lower
            and (
                "quel file" in normalized_lower
                or "il file" in normalized_lower
                or "questo file" in normalized_lower
            )
            and (
                "altra posizione" in normalized_lower
                or "un'altra posizione" in normalized_lower
                or "altra cartella" in normalized_lower
                or "un'altra cartella" in normalized_lower
            )
        ):
            return None

        source = self._extract_recent_file(context)
        destination_root = self._extract_project_directory(context)

        if source is None or destination_root is None:
            return None

        source_path = Path(source)
        root_path = Path(destination_root)
        source_parent = source_path.parent

        destination_parent = root_path

        if destination_parent.resolve(strict=False) == source_parent.resolve(strict=False):
            destination_parent = root_path / f"iris-copy-{uuid4().hex[:8]}"
            return AgentPlan(
                goal=goal,
                steps=(
                    AgentPlanStep(
                        tool_name="create_directory",
                        arguments={"path": str(destination_parent)},
                        description=(
                            "Crea una nuova posizione di destinazione nella radice "
                            "del progetto perché la posizione corrente coincide con essa."
                        ),
                        success_criteria=(
                            "La nuova directory di destinazione esiste."
                        ),
                    ),
                    AgentPlanStep(
                        tool_name="copy_path",
                        arguments={
                            "source": str(source_path),
                            "destination": str(
                                destination_parent / source_path.name
                            ),
                        },
                        description=(
                            "Copia il file già identificato nella nuova directory."
                        ),
                        success_criteria=(
                            "La copia del file esiste nella nuova posizione."
                        ),
                    ),
                ),
                decision=AgentDecision.DONE,
                message=None,
            )

        destination = destination_parent / (
            f"{source_path.stem}-copy-{uuid4().hex[:8]}{source_path.suffix}"
        )

        return AgentPlan(
            goal=goal,
            steps=(
                AgentPlanStep(
                    tool_name="copy_path",
                    arguments={
                        "source": str(source_path),
                        "destination": str(destination),
                    },
                    description=(
                        "Copia il file già identificato nella radice del progetto."
                    ),
                    success_criteria=(
                        "La copia del file esiste nella nuova posizione."
                    ),
                ),
            ),
            decision=AgentDecision.DONE,
            message=None,
        )

    @staticmethod
    def _extract_recent_file(context: str) -> str | None:
        for line in context.splitlines():
            try:
                value = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            if not isinstance(value, dict):
                continue

            output = value.get("output")
            if not isinstance(output, dict):
                continue

            tool_name = value.get("tool_name")

            if tool_name in {
                "copy_path",
                "move_path",
            }:
                destination = output.get("destination")
                if isinstance(destination, str) and destination.strip():
                    return destination

                source = output.get("source")
                if isinstance(source, str) and source.strip():
                    return source

            path = output.get("path")
            if isinstance(path, str) and path.strip():
                if tool_name in {
                    "read_file",
                    "write_file",
                }:
                    return path

                if (
                    output.get("is_file") is True
                    or output.get("type") == "file"
                ):
                    return path

        return None

    def _build_move_creation_fallback(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        context: str | None,
    ) -> AgentPlan | None:
        """Gestisce richieste di spostamento basate sullo stato verificato."""
        if not context:
            return None

        tool_names = {
            str(definition.get("name"))
            for definition in tool_definitions
            if isinstance(definition, dict)
        }

        if "move_path" not in tool_names:
            return None

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            goal.strip(),
            flags=re.IGNORECASE,
        )
        normalized_lower = normalized.lower()

        if "sposta" not in normalized_lower:
            return None

        source = self._extract_recent_file(context)
        destination_root = self._extract_project_directory(context)

        if source is None or destination_root is None:
            return None

        source_path = Path(source).resolve(strict=False)
        root_path = Path(destination_root).resolve(strict=False)
        destination_parent = root_path / f"iris-move-{uuid4().hex[:8]}"
        destination = destination_parent / source_path.name

        return AgentPlan(
            goal=goal,
            steps=(
                AgentPlanStep(
                    tool_name="create_directory",
                    arguments={
                        "path": str(destination_parent),
                    },
                    description=(
                        "Crea una nuova directory di destinazione separata dalla "
                        "posizione corrente del file."
                    ),
                    success_criteria=(
                        "La nuova directory di destinazione esiste."
                    ),
                ),
                AgentPlanStep(
                    tool_name="move_path",
                    arguments={
                        "source": str(source_path),
                        "destination": str(destination),
                    },
                    description=(
                        "Sposta il file già identificato nella nuova directory."
                    ),
                    success_criteria=(
                        "La destinazione esiste nella nuova directory e il percorso "
                        "sorgente non esiste più."
                    ),
                ),
            ),
            decision=AgentDecision.DONE,
            message=None,
        )

    def _build_directory_creation_fallback(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        context: str | None,
    ) -> AgentPlan | None:
        """Gestisce richieste generiche di creazione directory dal contesto reale."""
        if not context:
            return None

        tool_names = {
            str(definition.get("name"))
            for definition in tool_definitions
            if isinstance(definition, dict)
        }

        if "create_directory" not in tool_names:
            return None

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            goal.strip(),
            flags=re.IGNORECASE,
        )

        normalized_lower = normalized.lower()

        if not (
            "crea " in normalized_lower
            and (
                "cartella" in normalized_lower
                or "directory" in normalized_lower
            )
        ):
            return None

        parent = self._extract_project_directory(context)

        if parent is None:
            return None

        name_match = re.search(
            r"(?:cartella|directory)\s+(?:chiamata|denominata|di nome)\s+[\"']?([^\"'.,;]+)",
            normalized,
            flags=re.IGNORECASE,
        )

        requested_name = (
            name_match.group(1).strip()
            if name_match is not None
            else ""
        )

        if requested_name:
            safe_name = Path(requested_name).name.strip()
        else:
            safe_name = f"iris-test-{uuid4().hex[:8]}"

        if not safe_name or safe_name in {".", ".."}:
            safe_name = f"iris-test-{uuid4().hex[:8]}"

        path = str(Path(parent) / safe_name)

        return AgentPlan(
            goal=goal,
            steps=(
                AgentPlanStep(
                    tool_name="create_directory",
                    arguments={
                        "path": path,
                    },
                    description=(
                        "Crea una nuova directory nel percorso di progetto "
                        "individuato dal sistema."
                    ),
                    success_criteria=(
                        "La directory richiesta esiste nel percorso "
                        "individuato e può essere usata dagli step successivi."
                    ),
                ),
            ),
            decision=AgentDecision.DONE,
            message=None,
        )

    @staticmethod
    def _extract_project_directory(context: str) -> str | None:
        prefixes = (
            "- RADICE GIT DEL PROGETTO: ",
            "- DIRECTORY DI LAVORO CORRENTE: ",
        )

        for line in context.splitlines():
            for prefix in prefixes:
                if line.startswith(prefix):
                    value = line[len(prefix):].strip()
                    if value:
                        return value

        return None

    def _build_file_creation_fallback(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
        context: str | None,
    ) -> AgentPlan | None:
        """Gestisce richieste generiche di creazione file usando stato verificato."""
        if not context:
            return None

        tool_names = {
            str(definition.get("name"))
            for definition in tool_definitions
            if isinstance(definition, dict)
        }

        if "write_file" not in tool_names:
            return None

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            goal.strip(),
            flags=re.IGNORECASE,
        ).lower()

        if "crea" not in normalized or "file" not in normalized:
            return None

        references_directory = any(
            marker in normalized
            for marker in (
                "quella cartella",
                "questa cartella",
                "la cartella",
                "nella cartella",
            )
        )

        if not references_directory:
            return None

        directory = self._extract_recent_directory(context)

        if directory is None:
            return None

        filename_match = re.search(
            r"(?:file|un file)\s+(?:chiamato|denominato|di nome)\s+[\"']?([^\"'.,;]+)",
            goal,
            flags=re.IGNORECASE,
        )

        filename = (
            filename_match.group(1).strip()
            if filename_match is not None
            else f"{uuid4().hex}.txt"
        )

        if not filename:
            filename = f"{uuid4().hex}.txt"

        content_match = re.search(
            r"scriv(?:i|ici)\s+(?:dentro(?:ci)?\s+)?[\"“‘]([^\"”’]+)[\"”’]",
            goal,
            flags=re.IGNORECASE,
        )

        content = (
            content_match.group(1).strip()
            if content_match is not None
            else "Testo creato da IRIS."
        )

        path = str(Path(directory) / filename)

        return AgentPlan(
            goal=goal,
            steps=(
                AgentPlanStep(
                    tool_name="write_file",
                    arguments={
                        "path": path,
                        "content": content,
                    },
                    description=(
                        f"Crea un file nella directory già individuata e "
                        "scrivici il testo richiesto."
                    ),
                    success_criteria=(
                        "Il file esiste nella directory individuata e "
                        "contiene il testo richiesto o il testo generato "
                        "per una richiesta volutamente generica."
                    ),
                ),
            ),
            decision=AgentDecision.DONE,
            message=None,
        )

    @staticmethod
    def _extract_recent_directory(context: str) -> str | None:
        for line in context.splitlines():
            try:
                value = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            if not isinstance(value, dict):
                continue

            output = value.get("output")
            if not isinstance(output, dict):
                continue

            path = output.get("path")
            if not isinstance(path, str) or not path.strip():
                continue

            if (
                output.get("type") == "directory"
                or output.get("is_directory") is True
                or value.get("tool_name") == "create_directory"
            ):
                return path

        return None

    @classmethod
    def _extract_application_open_requests(
        cls,
        goal: str,
    ) -> list[str]:
        """
        Estrae nomi di applicazioni da richieste del tipo:

            apri Discord
            apri VS Code e poi Discord
            avvia Opera, poi VS Code

        Non contiene nomi applicativi hardcoded.
        """

        normalized = (
            goal.strip()
        )

        if not normalized:
            return []

        match = re.match(
            r"^\s*(?:/agent\s+)?"
            r"(?:apri|avvia|lancia|esegui)\s+"
            r"(.+?)\s*$",
            normalized,
            flags=re.IGNORECASE,
        )

        if match is None:
            return []

        remainder = match.group(
            1
        ).strip()

        if not remainder:
            return []

        remainder = re.sub(
            r"\s+e\s+poi\s+",
            "\n",
            remainder,
            flags=re.IGNORECASE,
        )

        remainder = re.sub(
            r"\s+poi\s+",
            "\n",
            remainder,
            flags=re.IGNORECASE,
        )

        remainder = re.sub(
            r",\s*poi\s+",
            "\n",
            remainder,
            flags=re.IGNORECASE,
        )

        remainder = re.sub(
            r";\s*",
            "\n",
            remainder,
        )

        parts = [
            part.strip()
            for part in remainder.splitlines()
            if part.strip()
        ]

        if not parts:
            return []

        cleaned: list[str] = []

        for part in parts:
            value = part.strip()

            value = re.sub(
                r"^(?:e\s+)?(?:poi\s+)",
                "",
                value,
                flags=re.IGNORECASE,
            )

            value = re.sub(
                r"\s+(?:e|poi)\s*$",
                "",
                value,
                flags=re.IGNORECASE,
            )

            value = value.strip(
                " ,.;"
            )

            if value:
                cleaned.append(
                    value
                )

        return cleaned

    # ========================================================================
    # GUI FALLBACK
    # ========================================================================

    def _build_gui_control_fallback(
        self,
        goal: str,
        tool_definitions: list[dict[str, Any]],
    ) -> AgentPlan | None:
        """
        Fallback per alcune intenzioni GUI atomiche e non ambigue.

        Non dipende da applicazioni specifiche.
        """

        tool_names = {
            str(
                definition.get(
                    "name"
                )
            )
            for definition in tool_definitions
            if isinstance(
                definition,
                dict,
            )
        }

        if (
            "press_key" not in tool_names
            and "type_text" not in tool_names
            and "set_clipboard" not in tool_names
            and "get_clipboard" not in tool_names
        ):
            return None

        normalized = (
            goal.strip()
            .lower()
        )

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            normalized,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        ).strip()

        if "type_text" in tool_names:
            text_value = (
                self._extract_text_input(
                    goal
                )
            )

            if text_value is not None:
                return AgentPlan(
                    goal=goal,
                    steps=(
                        AgentPlanStep(
                            tool_name="type_text",
                            arguments={
                                "text": text_value,
                            },
                            description=(
                                "Inserisci il testo richiesto "
                                "nella finestra attiva."
                            ),
                            success_criteria=(
                                "Il testo richiesto è stato "
                                "inserito nella finestra attiva."
                            ),
                        ),
                    ),
                    decision=AgentDecision.DONE,
                    message=None,
                )

        if "set_clipboard" in tool_names:
            clipboard_text = (
                self._extract_clipboard_set_text(
                    goal
                )
            )

            if clipboard_text is not None:
                return AgentPlan(
                    goal=goal,
                    steps=(
                        AgentPlanStep(
                            tool_name="set_clipboard",
                            arguments={
                                "text": clipboard_text,
                            },
                            description=(
                                "Copia il testo richiesto "
                                "negli appunti di Windows."
                            ),
                            success_criteria=(
                                "Il testo richiesto è presente "
                                "negli appunti di Windows."
                            ),
                        ),
                    ),
                    decision=AgentDecision.DONE,
                    message=None,
                )

        if "get_clipboard" in tool_names:
            if normalized in {
                "leggi gli appunti",
                "leggi appunti",
                "leggi il clipboard",
                "leggi clipboard",
                "leggi il contenuto degli appunti",
                "leggi il contenuto del clipboard",
                "mostrami gli appunti",
                "mostra gli appunti",
            }:
                return AgentPlan(
                    goal=goal,
                    steps=(
                        AgentPlanStep(
                            tool_name="get_clipboard",
                            arguments={},
                            description=(
                                "Leggi il testo attualmente "
                                "presente negli appunti di Windows."
                            ),
                            success_criteria=(
                                "Il contenuto degli appunti è stato "
                                "recuperato correttamente."
                            ),
                        ),
                    ),
                    decision=AgentDecision.DONE,
                    message=None,
                )

        if "press_key" not in tool_names:
            return None

        if "press_key" in tool_names:
            if normalized in {
                "copia",
                "copia il testo",
                "copia il contenuto",
                "copia tutto",
                "copia tutto il testo",
                "copia tutto il contenuto",
            }:
                return AgentPlan(
                    goal=goal,
                    steps=(
                        AgentPlanStep(
                            tool_name="press_key",
                            arguments={
                                "key": "CTRL+C",
                            },
                            description=(
                                "Copia negli appunti il contenuto "
                                "selezionato nella finestra attiva."
                            ),
                            success_criteria=(
                                "Il contenuto selezionato è stato "
                                "copiato negli appunti."
                            ),
                        ),
                    ),
                    decision=AgentDecision.DONE,
                    message=None,
                )

            if normalized in {
                "incolla",
                "incolla gli appunti",
                "incolla il contenuto",
                "incolla il testo",
            }:
                return AgentPlan(
                    goal=goal,
                    steps=(
                        AgentPlanStep(
                            tool_name="press_key",
                            arguments={
                                "key": "CTRL+V",
                            },
                            description=(
                                "Incolla il contenuto degli appunti "
                                "nella finestra attiva."
                            ),
                            success_criteria=(
                                "Il contenuto degli appunti è stato "
                                "inserito nella finestra attiva."
                            ),
                        ),
                    ),
                    decision=AgentDecision.DONE,
                    message=None,
                )

        if normalized in {
            "seleziona tutto",
            "seleziona tutto il testo",
            "seleziona tutto il contenuto",
        }:
            return AgentPlan(
                goal=goal,
                steps=(
                    AgentPlanStep(
                        tool_name="press_key",
                        arguments={
                            "key": "CTRL+A",
                        },
                        description=(
                            "Seleziona tutto il contenuto "
                            "della finestra attiva."
                        ),
                        success_criteria=(
                            "Il contenuto della finestra attiva "
                            "risulta selezionato."
                        ),
                    ),
                ),
                decision=AgentDecision.DONE,
                message=None,
            )

        if normalized in {
            "cancella il testo",
            "elimina il testo",
            "cancella tutto il testo",
            "elimina tutto il testo",
            "cancella tutto",
            "elimina tutto",
            "cancella il contenuto",
            "elimina il contenuto",
        }:
            return AgentPlan(
                goal=goal,
                steps=(
                    AgentPlanStep(
                        tool_name="press_key",
                        arguments={
                            "key": "CTRL+A",
                        },
                        description=(
                            "Seleziona tutto il contenuto "
                            "prima della cancellazione."
                        ),
                        success_criteria=(
                            "Tutto il contenuto della finestra "
                            "attiva è stato selezionato."
                        ),
                    ),
                    AgentPlanStep(
                        tool_name="press_key",
                        arguments={
                            "key": "DELETE",
                        },
                        description=(
                            "Cancella il contenuto selezionato."
                        ),
                        success_criteria=(
                            "Il contenuto precedentemente "
                            "selezionato è stato eliminato."
                        ),
                    ),
                ),
                decision=AgentDecision.DONE,
                message=None,
            )

        return None

    @staticmethod
    def _extract_clipboard_set_text(
        goal: str,
    ) -> str | None:
        normalized = goal.strip()

        if not normalized:
            return None

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).strip()

        match = re.match(
            r"^(copia|metti\s+negli\s+appunti|metti\s+nel\s+clipboard)\s+"
            r"(.+?)\s*$",
            normalized,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        command = match.group(
            1
        ).strip().lower()

        text = match.group(
            2
        ).strip()

        if (
            command == "copia"
            and text.lower()
            in {
                "il testo",
                "il contenuto",
                "tutto",
                "tutto il testo",
                "tutto il contenuto",
            }
        ):
            return None

        if not text:
            return None

        quote_pairs = (
            ('"', '"'),
            ("'", "'"),
            ("“", "”"),
            ("‘", "’"),
        )

        for opening, closing in quote_pairs:
            if (
                len(text) >= 2
                and text.startswith(opening)
                and text.endswith(closing)
            ):
                text = text[
                    1:-1
                ].strip()
                break

        if not text:
            return None

        return text

    @staticmethod
    def _extract_text_input(
        goal: str,
    ) -> str | None:
        normalized = goal.strip()

        if not normalized:
            return None

        normalized = re.sub(
            r"^\s*/agent\s+",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).strip()

        match = re.match(
            r"^(?:scrivi|digita|inserisci)\s+"
            r"(.+?)\s*$",
            normalized,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        text = match.group(
            1
        ).strip()

        if not text:
            return None

        quote_pairs = (
            ('"', '"'),
            ("'", "'"),
            ("“", "”"),
            ("‘", "’"),
        )

        for opening, closing in quote_pairs:
            if (
                len(text) >= 2
                and text.startswith(opening)
                and text.endswith(closing)
            ):
                text = text[
                    1:-1
                ].strip()
                break

        if not text:
            return None

        return text

    # ========================================================================
    # SCHEMA
    # ========================================================================

    def _build_plan_schema(
        self,
        tool_definitions: list[dict[str, Any]] | None,
        minimum_steps: int = 1,
    ) -> dict[str, Any]:
        argument_properties: dict[
            str,
            Any,
        ] = {}

        for definition in (
            tool_definitions or []
        ):
            if not isinstance(
                definition,
                dict,
            ):
                continue

            schema = definition.get(
                "input_schema"
            )

            if not isinstance(
                schema,
                dict,
            ):
                continue

            properties = schema.get(
                "properties"
            )

            if not isinstance(
                properties,
                dict,
            ):
                continue

            for name, value in properties.items():
                if (
                    isinstance(
                        name,
                        str,
                    )
                    and isinstance(
                        value,
                        dict,
                    )
                ):
                    argument_properties.setdefault(
                        name,
                        value,
                    )

        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                },
                "decision": {
                    "type": "string",
                    "enum": [
                        "done",
                        "continue",
                        "ask_user",
                    ],
                },
                "message": {
                    "type": [
                        "string",
                        "null",
                    ],
                },
                "steps": {
                    "type": "array",
                    "minItems": max(
                        1,
                        minimum_steps,
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {
                                "type": "string",
                            },
                            "arguments": {
                                "type": "object",
                                "properties": (
                                    argument_properties
                                ),
                                "additionalProperties": False,
                            },
                            "description": {
                                "type": "string",
                            },
                            "success_criteria": {
                                "type": [
                                    "string",
                                    "null",
                                ],
                            },
                        },
                        "required": [
                            "tool_name",
                            "arguments",
                            "description",
                            "success_criteria",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": [
                "goal",
                "decision",
                "message",
                "steps",
            ],
            "additionalProperties": False,
        }

    # ========================================================================
    # SYSTEM PROMPT
    # ========================================================================

    def _build_system_prompt(
        self,
        tool_definitions: list[dict[str, Any]] | None,
        context: str | None,
        observations: list[AgentObservation] | None,
    ) -> str:
        system_content = (
            "Sei il Planner di IRIS.\n"
            "Trasforma l'obiettivo dell'utente in un piano "
            "completo di azioni eseguibili.\n\n"

            "Il Core di IRIS eseguirà il piano e controllerà "
            "permessi, strumenti e risultati.\n\n"

            "REGOLE FONDAMENTALI:\n"
            "- usa esclusivamente i tool disponibili;\n"
            "- non inventare tool;\n"
            "- non inventare argomenti;\n"
            "- ogni azione distinta richiesta dall'utente "
            "deve avere uno step dedicato;\n"
            "- non fermarti alla prima azione se l'obiettivo "
            "richiede altre azioni;\n"
            "- per un obiettivo composto usa più step ordinati;\n"
            "- gli step devono rappresentare l'intera sequenza "
            "necessaria per completare l'obiettivo;\n"
            "- arguments deve contenere ESATTAMENTE gli argomenti "
            "del tool;\n"
            "- tutti gli argomenti obbligatori dello schema devono "
            "essere presenti;\n"
            "- non usare arguments={} quando il tool richiede "
            "parametri;\n"
            "- success_criteria deve descrivere cosa deve risultare "
            "vero dopo quello specifico step;\n"
            "- la verifica dei singoli step non sostituisce "
            "la copertura dell'obiettivo completo;\n"
            "- decision=done SOLO quando l'intero obiettivo è "
            "coperto dagli step;\n"
            "- decision=continue quando dopo gli step eseguiti "
            "servirà ulteriore pianificazione;\n"
            "- decision=ask_user quando manca un'informazione "
            "necessaria per scegliere correttamente un'azione;\n"
            "- l'esistenza o meno di un programma installato NON "
            "è da sola una ragione per usare ask_user: quando "
            "l'utente chiede di aprire un'app, pianifica "
            "open_application e lascia che il tool verifichi "
            "se l'app esiste;\n"
            "- le OSSERVAZIONI rappresentano lo stato reale "
            "dell'esecuzione precedente;\n"
            "- un'azione con success=True e verified=True "
            "è già completata e non deve essere ripetuta "
            "durante il replan, salvo richiesta esplicita "
            "dell'utente;\n"
            "- non produrre campi extra.\n"
            "- non assumere che applicazioni, directory, file, comandi "
            "o altre risorse abbiano nomi o percorsi hardcoded;\n"
            "- quando una risorsa necessaria non è già identificata "
            "nel contesto, usa prima un tool di discovery disponibile;\n"
            "- per il filesystem usa inspect_path, list_directory e "
            "search_files per trovare dinamicamente ciò che serve;\n"
            "- per applicazioni usa discover_applications o "
            "open_application e lascia che il sistema risolva il nome;\n"
            "- per processi e caratteristiche del sistema usa i tool "
            "di discovery invece di inventare informazioni;\n"
            "- per un comando richiesto dall'utente usa run_command "
            "con il comando reale, senza cercare corrispondenze in "
            "liste di comandi predefinite;\n"
            "- se un'informazione può essere ottenuta interrogando "
            "il PC, non chiedere all'utente di fornirla a meno che "
            "l'informazione non sia realmente non disponibile;\n"
            "- usa lo STATO OPERATIVO RECENTE come fonte reale per i risultati "
            "delle richieste agent precedenti; risolvi riferimenti come 'quella "
            "cartella' usando i percorsi osservati, senza inventarne di nuovi;\n"
            "- se l'utente chiede di creare un file dentro una directory già "
            "identificata dallo stato recente, usa esattamente il percorso completo "
            "della directory osservata come parent del nuovo file; non usare solo "
            "il nome finale della directory e non sostituire il percorso con uno "
            "inventato;\n"
            "- per richieste semplici di creazione di una nuova cartella o "
            "directory, usa la directory di progetto reale fornita dal contesto "
            "e crea il percorso necessario; non trasformare una richiesta "
            "semplice in ask_user solo perché il modello non ha costruito "
            "correttamente il JSON;\n"
            "- il contesto può contenere dati ambientali reali del processo, "
            "come la directory di lavoro corrente e la radice Git del progetto;\n"
            "- per richieste come 'directory del progetto', usa esattamente "
            "la radice Git presente nel contesto quando disponibile, "
            "altrimenti usa esattamente la directory di lavoro corrente; "
            "non sintetizzare o inventare percorsi assoluti;\n"
            "- per 'copia quel file in un'altra posizione', quando il file è "
            "identificato nello STATO OPERATIVO RECENTE ma la destinazione non "
            "è specificata, usa la radice del progetto come destinazione secondaria "
            "e assegna un nome di copia univoco; non usare ask_user solo per questa "
            "ambiguità quando esiste una destinazione ragionevole e verificabile;\n"
            "- per qualsiasi richiesta che contiene 'sposta', usa SEMPRE move_path "
            "e mai copy_path; quando la destinazione non è esplicitata ma il file è "
            "identificato nello STATO OPERATIVO RECENTE, scegli una destinazione "
            "distinta e verificabile nella radice del progetto; non usare ask_user "
            "e non lasciare mai sorgente e destinazione uguali;\n\n"

            "SEMANTICA GUI:\n"
            "- 'seleziona tutto' -> press_key con key='CTRL+A';\n"
            "- 'cancella il testo' o 'elimina il testo' -> "
            "se non hai prova che il testo sia già selezionato, "
            "usa prima CTRL+A e poi DELETE;\n"
            "- 'scrivi', 'digita' o 'inserisci' testo -> type_text;\n"
            "- non usare type_text per premere tasti o combinazioni;\n"
            "- non usare press_key per inserire testo arbitrario.\n\n"

            "ESEMPIO DI DECOMPOSIZIONE:\n"
            "Obiettivo: 'apri il blocco note, portalo in primo piano "
            "e scrivici ciao'\n"
            "Piano corretto:\n"
            "1. open_application\n"
            "2. focus_window\n"
            "3. type_text\n\n"

            "Obiettivo: 'apri VS Code e poi Discord'\n"
            "Piano corretto:\n"
            "1. open_application con name='VS Code'\n"
            "2. open_application con name='Discord'\n\n"

            "Obiettivo: 'apri un programma che potrebbe non essere "
            "installato'\n"
            "Piano corretto:\n"
            "1. open_application con il nome richiesto\n\n"

            "Obiettivo: 'seleziona tutto il testo'\n"
            "Piano corretto:\n"
            "1. press_key con key='CTRL+A'\n\n"

            "Obiettivo: 'cancella il testo'\n"
            "Piano corretto:\n"
            "1. press_key con key='CTRL+A'\n"
            "2. press_key con key='DELETE'\n\n"

            "NON è corretto produrre solo il primo step di un "
            "obiettivo composto e dichiararlo completato.\n"
        )

        if tool_definitions:
            tool_context = (
                self._build_compact_tool_context(
                    tool_definitions
                )
            )

            if tool_context:
                system_content += (
                    "\nTOOL DISPONIBILI:\n"
                    + tool_context
                )

        if context:
            compact_context = (
                self._compact_text(
                    context,
                    max_chars=1400,
                )
            )

            if compact_context:
                system_content += (
                    "\n\nCONTESTO:\n"
                    + compact_context
                )

        if observations:
            compact_observations = (
                self._build_compact_observations(
                    observations
                )
            )

            if compact_observations:
                system_content += (
                    "\n\nOSSERVAZIONI:\n"
                    + compact_observations
                )

        return (
            system_content
            + "\n\n"
            "Il risultato deve essere esclusivamente "
            "l'oggetto JSON conforme allo schema imposto "
            "dal sistema."
        )

    # ========================================================================
    # TOOL CONTEXT
    # ========================================================================

    @staticmethod
    def _build_compact_tool_context(
        tool_definitions: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = []

        for definition in tool_definitions:
            if not isinstance(
                definition,
                dict,
            ):
                continue

            name = definition.get(
                "name",
                "",
            )

            description = definition.get(
                "description",
                "",
            )

            schema = definition.get(
                "input_schema",
                {},
            )

            if (
                not isinstance(
                    name,
                    str,
                )
                or not name.strip()
            ):
                continue

            if not isinstance(
                description,
                str,
            ):
                description = ""

            compact_schema = json.dumps(
                schema,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )

            lines.append(
                (
                    f"- {name}: "
                    f"{description}; "
                    f"schema={compact_schema}"
                )
            )

        return "\n".join(
            lines
        )

    # ========================================================================
    # OBSERVATIONS
    # ========================================================================

    @staticmethod
    def _build_compact_observations(
        observations: list[AgentObservation],
    ) -> str:
        lines: list[str] = []

        for observation in observations:
            line = (
                f"step={observation.step_index}; "
                f"tool={observation.tool_name}; "
                f"success={observation.success}; "
                f"verified={observation.verified}"
            )

            if observation.error:
                line += (
                    f"; error={observation.error}"
                )

            if observation.output is not None:
                output = (
                    AgentPlanner._compact_text(
                        str(
                            observation.output
                        ),
                        max_chars=350,
                    )
                )

                if output:
                    line += (
                        f"; output={output}"
                    )

            lines.append(
                line
            )

        return "\n".join(
            lines
        )

    # ========================================================================
    # TEXT HELPERS
    # ========================================================================

    @staticmethod
    def _compact_text(
        value: str,
        max_chars: int,
    ) -> str:
        if not isinstance(
            value,
            str,
        ):
            return ""

        value = value.strip()

        if not value:
            return ""

        if len(value) <= max_chars:
            return value

        return (
            value[:max_chars]
            + "\n[contesto troncato]"
        )

    @staticmethod
    def _looks_like_multi_step_goal(
        goal: str,
    ) -> bool:
        normalized = (
            goal.strip()
            .lower()
        )

        if not normalized:
            return False

        structural_text = (
            AgentPlanner._strip_quoted_text(
                normalized
            )
        )

        markers = (
            " e ",
            " poi ",
            " dopo ",
            " successivamente ",
            " prima ",
            " infine ",
            " quindi ",
            " dopodiché ",
            ",",
            ";",
            " mentre ",
            " dopodopo ",
            " successivo ",
        )

        if any(
            marker in structural_text
            for marker in markers
        ):
            return True

        action_markers = (
            "apri ",
            "chiudi ",
            "scrivi ",
            "digita ",
            "inserisci ",
            "premi ",
            "clicca ",
            "sposta ",
            "porta ",
            "metti ",
            "crea ",
            "salva ",
            "leggi ",
            "modifica ",
            "esegui ",
            "avvia ",
            "ferma ",
            "vai ",
            "manda ",
            "seleziona ",
            "cancella ",
            "elimina ",
            "copia ",
            "incolla ",
        )

        action_count = sum(
            1
            for marker
            in action_markers
            if marker in structural_text
        )

        if action_count >= 2:
            return True

        if normalized in {
            "cancella il testo",
            "elimina il testo",
            "cancella tutto il testo",
            "elimina tutto il testo",
            "cancella tutto",
            "elimina tutto",
            "cancella il contenuto",
            "elimina il contenuto",
        }:
            return True

        return len(structural_text) >= 100

    @staticmethod
    def _strip_quoted_text(
        value: str,
    ) -> str:
        """Rimuove il contenuto tra virgolette per i controlli strutturali."""

        if not value:
            return value

        quote_pairs = {
            '"': '"',
            "“": "”",
            "‘": "’",
        }

        result: list[str] = []
        closing_quote: str | None = None

        for character in value:
            if closing_quote is not None:
                if character == closing_quote:
                    closing_quote = None
                else:
                    result.append(" ")
                continue

            closing = quote_pairs.get(
                character
            )

            if closing is not None:
                closing_quote = closing
                result.append(" ")
                continue

            result.append(character)

        return "".join(result)

    # ========================================================================
    # PLAN VALIDATION
    # ========================================================================

    def _validate_plan_against_tools(
        self,
        plan: AgentPlan,
        tool_definitions: list[dict[str, Any]],
    ) -> str | None:
        definitions = {
            str(
                item.get("name")
            ): item
            for item in tool_definitions
            if (
                isinstance(
                    item,
                    dict,
                )
                and isinstance(
                    item.get("name"),
                    str,
                )
            )
        }

        for index, step in enumerate(
            plan.steps,
            start=1,
        ):
            definition = definitions.get(
                step.tool_name
            )

            if definition is None:
                return (
                    f"step {index}: "
                    f"tool inesistente: "
                    f"{step.tool_name}"
                )

            schema = definition.get(
                "input_schema",
                {},
            )

            if not isinstance(
                schema,
                dict,
            ):
                continue

            properties = schema.get(
                "properties",
                {},
            )

            required = schema.get(
                "required",
                [],
            )

            if not isinstance(
                properties,
                dict,
            ):
                properties = {}

            if not isinstance(
                required,
                list,
            ):
                required = []

            for required_name in required:
                if required_name not in (
                    step.arguments
                ):
                    return (
                        f"step {index} "
                        f"({step.tool_name}): "
                        f"argomento obbligatorio "
                        f"mancante: "
                        f"{required_name}"
                    )

            if (
                schema.get(
                    "additionalProperties"
                )
                is False
            ):
                unknown = [
                    key
                    for key in step.arguments
                    if key not in properties
                ]

                if unknown:
                    return (
                        f"step {index} "
                        f"({step.tool_name}): "
                        f"argomenti non consentiti: "
                        f"{', '.join(map(str, unknown))}"
                    )

        return None

    # ========================================================================
    # GOAL COVERAGE
    # ========================================================================

    def _validate_plan_coverage(
        self,
        goal: str,
        plan: AgentPlan,
        tool_definitions: list[dict[str, Any]],
    ) -> str | None:
        """
        Controllo leggero e generalista sulla copertura dell'obiettivo.

        Non contiene nomi specifici di applicazioni.
        """

        if not self._looks_like_multi_step_goal(
            goal
        ):
            return None

        if len(plan.steps) >= 2:
            return None

        tool_context = (
            self._build_compact_tool_context(
                tool_definitions
            )
        )

        if not tool_context:
            return (
                "L'obiettivo appare composto, "
                "ma il piano contiene un solo step."
            )

        return (
            "L'obiettivo appare composto, "
            "ma il piano contiene un solo step. "
            "Devi scomporre l'obiettivo in tutte "
            "le azioni necessarie."
        )

    # ========================================================================
    # RESPONSE DECODING
    # ========================================================================

    def _decode_response(
        self,
        response: str,
    ) -> dict[str, Any]:
        if not isinstance(
            response,
            str,
        ):
            raise TypeError(
                "La risposta del planner deve essere una stringa."
            )

        content = response.strip()

        if not content:
            raise ValueError(
                "Il planner ha restituito una risposta vuota."
            )

        for _ in range(4):
            content = (
                self._strip_markdown_json(
                    content
                )
            )

            parsed = (
                self._parse_json_value(
                    content
                )
            )

            if isinstance(
                parsed,
                dict,
            ):
                response_type = parsed.get(
                    "type"
                )

                if response_type == "final":
                    inner = parsed.get(
                        "content"
                    )

                    if isinstance(
                        inner,
                        str,
                    ):
                        content = inner.strip()
                        continue

                    if isinstance(
                        inner,
                        dict,
                    ):
                        return inner

                    raise ValueError(
                        "La risposta final del planner "
                        "non contiene un contenuto valido."
                    )

                if self._looks_like_plan(
                    parsed
                ):
                    return parsed

                for key in (
                    "content",
                    "result",
                    "plan",
                    "response",
                    "output",
                ):
                    nested = parsed.get(
                        key
                    )

                    if (
                        isinstance(
                            nested,
                            dict,
                        )
                        and self._looks_like_plan(
                            nested
                        )
                    ):
                        return nested

                    if (
                        isinstance(
                            nested,
                            str,
                        )
                        and nested.strip()
                    ):
                        content = (
                            nested.strip()
                        )
                        break
                else:
                    return parsed

                continue

            if isinstance(
                parsed,
                str,
            ):
                content = parsed.strip()
                continue

            raise ValueError(
                "Il planner non ha restituito un JSON valido."
            )

        raise ValueError(
            "Il planner non ha restituito "
            "un oggetto JSON valido dopo "
            "la decodifica."
        )

    @staticmethod
    def _looks_like_plan(
        data: dict[str, Any],
    ) -> bool:
        return any(
            key in data
            for key in (
                "steps",
                "actions",
                "tool_name",
                "tool",
                "name",
            )
        )

    @staticmethod
    def _strip_markdown_json(
        content: str,
    ) -> str:
        if not content.startswith(
            "```"
        ):
            return content

        lines = content.splitlines()

        if (
            lines
            and lines[0]
            .strip()
            .startswith("```")
        ):
            lines = lines[1:]

        if (
            lines
            and lines[-1]
            .strip()
            == "```"
        ):
            lines = lines[:-1]

        return "\n".join(
            lines
        ).strip()

    @staticmethod
    def _parse_json_value(
        content: str,
    ) -> Any:
        try:
            return json.loads(
                content
            )

        except json.JSONDecodeError as error:
            start = content.find(
                "{"
            )

            end = content.rfind(
                "}"
            )

            if (
                start == -1
                or end <= start
            ):
                raise ValueError(
                    "Il planner non ha restituito un JSON valido."
                ) from error

            try:
                return json.loads(
                    content[
                        start : end + 1
                    ]
                )

            except json.JSONDecodeError as nested_error:
                raise ValueError(
                    "Il planner non ha restituito un JSON valido."
                ) from nested_error

    # ========================================================================
    # NORMALIZATION
    # ========================================================================

    def _normalize_plan(
        self,
        data: dict[str, Any],
        fallback_goal: str,
    ) -> dict[str, Any]:
        normalized = dict(
            data
        )

        nested = (
            self._find_plan_container(
                normalized
            )
        )

        if nested is not None:
            merged = dict(
                nested
            )

            for key, value in normalized.items():
                if (
                    key
                    not in {
                        "plan",
                        "result",
                        "action",
                    }
                    and key not in merged
                ):
                    merged[key] = value

            normalized = merged

        returned_goal = normalized.get(
            "goal",
            fallback_goal,
        )

        normalized["goal"] = (
            returned_goal
            if isinstance(
                returned_goal,
                str,
            )
            else fallback_goal
        )

        normalized["decision"] = (
            self._normalize_decision(
                normalized.get(
                    "decision",
                    AgentDecision.DONE.value,
                )
            )
        )

        message = normalized.get(
            "message"
        )

        if (
            message is not None
            and not isinstance(
                message,
                str,
            )
        ):
            message = str(
                message
            )

        normalized["message"] = message

        raw_steps = normalized.get(
            "steps"
        )

        if raw_steps is None:
            for key in (
                "actions",
                "action_steps",
                "operations",
                "tools",
            ):
                candidate = normalized.get(
                    key
                )

                if candidate is not None:
                    raw_steps = candidate
                    break

        normalized_steps = (
            self._normalize_steps_value(
                raw_steps
            )
        )

        if normalized_steps is None:
            candidate = (
                self._extract_step_from_anywhere(
                    normalized
                )
            )

            if candidate is not None:
                normalized_steps = [
                    candidate
                ]

        normalized["steps"] = (
            self._deduplicate_steps(
                normalized_steps
            )
        )

        return normalized

    def _find_plan_container(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        for key in (
            "plan",
            "result",
            "action",
        ):
            value = data.get(
                key
            )

            if isinstance(
                value,
                str,
            ):
                try:
                    value = (
                        self._parse_json_value(
                            value
                        )
                    )
                except ValueError:
                    continue

            if (
                isinstance(
                    value,
                    dict,
                )
                and any(
                    k in value
                    for k in (
                        "steps",
                        "actions",
                        "tool_name",
                        "tool",
                        "name",
                        "function",
                    )
                )
            ):
                return value

        return None

    def _normalize_steps_value(
        self,
        value: Any,
    ) -> list[Any] | None:
        if value is None:
            return None

        if isinstance(
            value,
            list,
        ):
            return value

        if isinstance(
            value,
            tuple,
        ):
            return list(
                value
            )

        if isinstance(
            value,
            dict,
        ):
            nested_steps = value.get(
                "steps"
            )

            if nested_steps is not None:
                normalized = (
                    self._normalize_steps_value(
                        nested_steps
                    )
                )

                if normalized:
                    return normalized

            candidate = (
                self._step_from_dict(
                    value
                )
            )

            if candidate is not None:
                return [
                    candidate
                ]

            for key in (
                "actions",
                "action_steps",
                "operations",
                "tools",
                "items",
                "data",
            ):
                nested = value.get(
                    key
                )

                if nested is not None:
                    normalized = (
                        self._normalize_steps_value(
                            nested
                        )
                    )

                    if normalized:
                        return normalized

            for nested in value.values():
                normalized = (
                    self._normalize_steps_value(
                        nested
                    )
                )

                if normalized:
                    return normalized

            return None

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            if not text:
                return None

            try:
                parsed = (
                    self._parse_json_value(
                        text
                    )
                )
            except ValueError:
                parsed = None

            if parsed is not None:
                normalized = (
                    self._normalize_steps_value(
                        parsed
                    )
                )

                if normalized:
                    return normalized

            return [
                {
                    "tool_name": text,
                    "arguments": {},
                    "description": (
                        f"Esegui il tool {text}."
                    ),
                    "success_criteria": None,
                }
            ]

        return None

    @staticmethod
    def _deduplicate_steps(
        steps: list[Any] | None,
    ) -> list[Any] | None:
        if not steps:
            return steps

        result: list[Any] = []
        seen: set[str] = set()

        for step in steps:
            if isinstance(
                step,
                dict,
            ):
                tool_name = step.get(
                    "tool_name",
                    step.get(
                        "tool",
                        step.get(
                            "name",
                            "",
                        ),
                    ),
                )

                arguments = step.get(
                    "arguments",
                    step.get(
                        "args",
                        {},
                    ),
                )

                try:
                    key = json.dumps(
                        {
                            "tool_name": tool_name,
                            "arguments": arguments,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                except TypeError:
                    key = repr(
                        (
                            tool_name,
                            arguments,
                        )
                    )

                if key in seen:
                    continue

                seen.add(
                    key
                )

            result.append(
                step
            )

        return result

    def _extract_step_from_anywhere(
        self,
        value: Any,
    ) -> dict[str, Any] | None:
        if isinstance(
            value,
            dict,
        ):
            direct = (
                self._step_from_dict(
                    value
                )
            )

            if direct is not None:
                return direct

            for nested_value in value.values():
                found = (
                    self._extract_step_from_anywhere(
                        nested_value
                    )
                )

                if found is not None:
                    return found

            return None

        if isinstance(
            value,
            list,
        ):
            for item in value:
                found = (
                    self._extract_step_from_anywhere(
                        item
                    )
                )

                if found is not None:
                    return found

            return None

        if isinstance(
            value,
            str,
        ):
            try:
                parsed = (
                    self._parse_json_value(
                        value.strip()
                    )
                )
            except ValueError:
                return None

            return (
                self._extract_step_from_anywhere(
                    parsed
                )
            )

        return None

    # ========================================================================
    # STEP NORMALIZATION
    # ========================================================================

    def _step_from_dict(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        tool_name = data.get(
            "tool_name"
        )

        if not isinstance(
            tool_name,
            str,
        ):
            tool_name = data.get(
                "tool"
            )

        if not isinstance(
            tool_name,
            str,
        ):
            tool_name = data.get(
                "name"
            )

        if not isinstance(
            tool_name,
            str,
        ):
            function = data.get(
                "function"
            )

            if isinstance(
                function,
                dict,
            ):
                tool_name = function.get(
                    "name"
                )

        if (
            not isinstance(
                tool_name,
                str,
            )
            or not tool_name.strip()
        ):
            return None

        tool_name = (
            tool_name.strip()
        )

        arguments = data.get(
            "arguments"
        )

        if arguments is None:
            arguments = data.get(
                "args",
                {},
            )

        if isinstance(
            arguments,
            str,
        ):
            try:
                parsed_arguments = (
                    self._parse_json_value(
                        arguments
                    )
                )
            except ValueError:
                parsed_arguments = None

            if isinstance(
                parsed_arguments,
                dict,
            ):
                arguments = (
                    parsed_arguments
                )

        if not isinstance(
            arguments,
            dict,
        ):
            arguments = {}

        function = data.get(
            "function"
        )

        if isinstance(
            function,
            dict,
        ):
            function_arguments = (
                function.get(
                    "arguments"
                )
            )

            if isinstance(
                function_arguments,
                str,
            ):
                try:
                    parsed_arguments = (
                        self._parse_json_value(
                            function_arguments
                        )
                    )
                except ValueError:
                    parsed_arguments = None

                if isinstance(
                    parsed_arguments,
                    dict,
                ):
                    arguments = (
                        parsed_arguments
                    )

        description = data.get(
            "description",
            f"Esegui il tool {tool_name}.",
        )

        if not isinstance(
            description,
            str,
        ):
            description = (
                f"Esegui il tool {tool_name}."
            )

        success_criteria = data.get(
            "success_criteria"
        )

        if success_criteria is not None:
            success_criteria = str(
                success_criteria
            )

        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "description": description,
            "success_criteria": success_criteria,
        }

    # ========================================================================
    # DECISION
    # ========================================================================

    @staticmethod
    def _normalize_decision(
        value: Any,
    ) -> str:
        if isinstance(
            value,
            AgentDecision,
        ):
            return value.value

        if not isinstance(
            value,
            str,
        ):
            return AgentDecision.DONE.value

        normalized = (
            value.strip()
            .lower()
        )

        aliases = {
            "done": "done",
            "complete": "done",
            "completed": "done",
            "finish": "done",
            "finished": "done",
            "success": "done",
            "continue": "continue",
            "next": "continue",
            "keep_going": "continue",
            "keep-going": "continue",
            "ask_user": "ask_user",
            "ask-user": "ask_user",
            "ask user": "ask_user",
            "user": "ask_user",
        }

        return aliases.get(
            normalized,
            AgentDecision.DONE.value,
        )

    # ========================================================================
    # BUILD PLAN
    # ========================================================================

    def _build_plan(
        self,
        goal: str,
        data: dict[str, Any],
    ) -> AgentPlan:
        returned_goal = data.get(
            "goal",
            goal,
        )

        if not isinstance(
            returned_goal,
            str,
        ):
            raise ValueError(
                "Il campo 'goal' del piano non è valido."
            )

        decision_value = data.get(
            "decision",
            AgentDecision.DONE.value,
        )

        if not isinstance(
            decision_value,
            str,
        ):
            raise ValueError(
                "Il campo 'decision' del piano non è valido."
            )

        try:
            decision = AgentDecision(
                decision_value
            )
        except ValueError as error:
            raise ValueError(
                "La decisione del piano non è valida."
            ) from error

        message = data.get(
            "message"
        )

        if (
            message is not None
            and not isinstance(
                message,
                str,
            )
        ):
            raise ValueError(
                "Il campo 'message' del piano non è valido."
            )

        steps_data = data.get(
            "steps"
        )

        if not isinstance(
            steps_data,
            list,
        ):
            raise ValueError(
                "Il planner non ha prodotto "
                "uno step recuperabile dal JSON restituito."
            )

        if not steps_data:
            raise ValueError(
                "Il planner ha restituito un piano vuoto."
            )

        steps: list[
            AgentPlanStep
        ] = []

        for index, raw_step in enumerate(
            steps_data,
            start=1,
        ):
            if isinstance(
                raw_step,
                str,
            ):
                raw_step = {
                    "tool_name": raw_step,
                    "arguments": {},
                    "description": (
                        f"Esegui il tool {raw_step}."
                    ),
                    "success_criteria": None,
                }

            if not isinstance(
                raw_step,
                dict,
            ):
                raise ValueError(
                    f"Lo step {index} del piano non è valido."
                )

            normalized = (
                self._step_from_dict(
                    raw_step
                )
            )

            if normalized is None:
                raise ValueError(
                    (
                        f"Lo step {index} "
                        "non contiene un "
                        "tool_name valido."
                    )
                )

            steps.append(
                AgentPlanStep(
                    tool_name=(
                        normalized[
                            "tool_name"
                        ]
                    ),
                    arguments=(
                        normalized[
                            "arguments"
                        ]
                    ),
                    description=(
                        normalized[
                            "description"
                        ]
                    ),
                    success_criteria=(
                        normalized[
                            "success_criteria"
                        ]
                    ),
                )
            )

        return AgentPlan(
            goal=returned_goal,
            steps=tuple(
                steps
            ),
            decision=decision,
            message=message,
        )


__all__ = [
    "AgentPlanStep",
    "AgentPlan",
    "AgentPlanner",
]
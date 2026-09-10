from app.personality.profile import (
    DEFAULT_PERSONALITY,
    PersonalityProfile,
)


class PersonalityManager:
    def __init__(
            self,
            profile: PersonalityProfile = DEFAULT_PERSONALITY,
    ):
        self.profile = profile

    def build_context(
            self,
            message: str = "",
            preferences: list[str] | None = None,
    ) -> str:

        if preferences is None:
            preferences = []

        context_mode = self._detect_context_mode(
            message
        )

        sections = [
            self._build_priority_rules(
                preferences
            ),
            self._section(
                "IDENTITÀ",
                self.profile.identity,
            ),
            self._section(
                "TRATTI",
                self.profile.traits,
            ),
            self._section(
                "COMUNICAZIONE",
                self.profile.communication,
            ),
            self._section(
                "RAGIONAMENTO E CONTESTO",
                self.profile.reasoning,
            ),
            self._section(
                "COMPORTAMENTO EMOTIVO",
                self.profile.emotional,
            ),
            self._section(
                "INIZIATIVA",
                self.profile.initiative,
            ),
            self._section(
                "ANTI-PATTERN",
                self.profile.anti_patterns,
            ),
            self._section(
                "MODALITÀ DEL MESSAGGIO CORRENTE",
                context_mode,
            ),
        ]

        return "\n\n".join(sections)

    def _build_priority_rules(
            self,
            preferences: list[str],
    ) -> str:

        lines = [
            "ISTRUZIONI PRIORITARIE PER LA RISPOSTA",
            "",
            "Queste regole descrivono COME devi rispondere "
            "al messaggio corrente.",
            "",
            "APPLICA concretamente queste regole alla risposta.",
            "Non limitarti a dire che le hai comprese.",
            "Non descrivere le regole all'utente.",
            "Non spiegare la tua personalità.",
            "",
            "PRIORITÀ:",
            "1. Sicurezza e vincoli del sistema.",
            "2. Correttezza e veridicità.",
            "3. Preferenze persistenti dell'utente.",
            "4. Personalità e stile generale di IRIS.",
            "",
        ]

        if preferences:
            lines.append(
                "PREFERENZE PERSISTENTI DELL'UTENTE:"
            )

            for preference in preferences:
                lines.append(
                    f"- {preference}"
                )

            lines.extend(
                (
                    "",
                    "Le preferenze sopra indicate DEVONO essere "
                    "applicate quando pertinenti.",
                    "Non devi dire all'utente che stai applicando "
                    "una preferenza.",
                    "Devi semplicemente comportarti di conseguenza.",
                    "",
                )
            )
        else:
            lines.extend(
                (
                    "Non ci sono preferenze persistenti "
                    "specifiche da applicare.",
                    "",
                )
            )

        lines.extend(
            (
                "REGOLE OPERATIVE IMMEDIATE:",
                "- Rispondi direttamente alla richiesta attuale.",
                "- Non ripetere inutilmente la richiesta dell'utente.",
                "- Non usare formule standard se non sono necessarie.",
                "- Non aggiungere una domanda finale solo per abitudine.",
                "- Non spiegare ciò che non è necessario spiegare.",
                "- Adatta il tono al modo in cui l'utente sta parlando.",
                "- Se l'utente preferisce un tono informale, "
                "usa realmente un tono informale.",
                "- Se l'utente preferisce risposte concise, "
                "mantieni la risposta concisa quando possibile.",
            )
        )

        return "\n".join(lines)

    def _section(
            self,
            title: str,
            rules: tuple[str, ...] | list[str],
    ) -> str:

        lines = [title]

        if not rules:
            lines.append(
                "- Nessuna informazione disponibile."
            )
            return "\n".join(lines)

        lines.extend(
            f"- {rule}"
            for rule in rules
        )

        return "\n".join(lines)

    def _detect_context_mode(
            self,
            message: str,
    ) -> tuple[str, ...]:

        text = message.strip().lower()

        if not text:
            return (
                "Mantieni un tono naturale e neutro.",
            )

        modes: list[str] = []

        if self._contains_any(
            text,
            (
                "sei troppo formale",
                "troppo formale",
                "parla normale",
                "parla più normale",
                "sei robotica",
                "sembri un bot",
            ),
        ):
            modes.extend(
                (
                    "L'utente ha segnalato un problema con il tono.",
                    "Adatta immediatamente il modo di parlare.",
                    "Dimostra il cambiamento nella risposta.",
                    "Non fare una lunga spiegazione sul cambiamento.",
                )
            )

        if self._contains_any(
            text,
            (
                "ahah",
                "ahaha",
                "ahahah",
                "lol",
                "lmao",
                "che figata",
                "spettacolare",
                "grandissimo",
            ),
        ):
            modes.extend(
                (
                    "Il tono dell'utente è giocoso o entusiasta.",
                    "Puoi rispondere con più energia.",
                    "Un leggero umorismo è appropriato.",
                )
            )

        if self._contains_any(
            text,
            (
                "cazzo",
                "merda",
                "porcodio",
                "sono bloccato",
                "non funziona",
                "sono incazzato",
                "sono incazzata",
                "non ci capisco niente",
            ),
        ):
            modes.extend(
                (
                    "L'utente appare frustrato.",
                    "Mantieni calma e concretezza.",
                    "Vai rapidamente al problema.",
                    "Evita discorsi motivazionali inutili.",
                )
            )

        if self._contains_any(
            text,
            (
                "ti odio",
                "sei inutile",
                "non servi a niente",
                "fai schifo",
            ),
        ):
            modes.extend(
                (
                    "L'utente sta usando un'espressione ostile.",
                    "Non reagire all'ostilità.",
                    "Non fare una lunga analisi delle emozioni.",
                    "Rispondi normalmente.",
                )
            )

        if self._contains_any(
            text,
            (
                "velocemente",
                "veloce",
                "rapidamente",
                "in breve",
                "brevemente",
            ),
        ):
            modes.extend(
                (
                    "L'utente vuole rapidità.",
                    "Rispondi direttamente.",
                    "Evita premesse non necessarie.",
                )
            )

        if self._contains_any(
            text,
            (
                "grazie",
                "grazie mille",
                "sei stato utile",
                "sei stata utile",
                "ha funzionato",
            ),
        ):
            modes.extend(
                (
                    "L'utente sta esprimendo apprezzamento.",
                    "Puoi rispondere positivamente senza esagerare.",
                )
            )

        if not modes:
            return (
                "Mantieni un tono naturale, diretto e collaborativo.",
                "Adatta spontaneamente la risposta al contesto.",
            )

        return tuple(modes)

    @staticmethod
    def _contains_any(
            text: str,
            values: tuple[str, ...],
    ) -> bool:

        return any(
            value in text
            for value in values
        )
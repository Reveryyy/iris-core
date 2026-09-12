from __future__ import annotations

import shlex
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from prompt_toolkit import Application
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    Dimension,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from rich.console import Console
from rich.table import Table
from rich.text import Text

from app.ui.events import IRISEventBus
from app.ui.state import TerminalState


# ============================================================================
# PALETTE
# ============================================================================

BG = "#080808"
SURFACE = "#0D0D0D"
SURFACE_2 = "#121212"
SURFACE_3 = "#181818"

TEXT = "#E6E6E6"
SOFT = "#B0B0B0"
MUTED = "#737373"
DIM = "#3E3E3E"

# Quasi nessun colore.
ACCENT = "#D0D0D0"
ACCENT_2 = "#B8B8B8"

SUCCESS = "#A5A5A5"
WARNING = "#929292"
ERROR = "#9A9A9A"
TOOL = "#B5B5B5"


# ============================================================================
# STYLE
# ============================================================================

PROMPT_STYLE = Style.from_dict(
    {
        "root": (
            f"bg:{BG} "
            f"{TEXT}"
        ),

        # Header
        "header": TEXT,
        "header.accent": f"bold {ACCENT}",
        "header.muted": MUTED,
        "header.model": SOFT,
        "header.forced": ACCENT,

        # Transcript
        "user": TEXT,
        "user.prompt": f"bold {ACCENT}",
        "iris": TEXT,
        "iris.label": f"bold {ACCENT}",
        "iris.meta": MUTED,
        "system": MUTED,

        # Composer
        "composer": (
            f"bg:{SURFACE} "
            f"{TEXT}"
        ),
        "composer.input": (
            f"bg:{SURFACE} "
            f"{TEXT}"
        ),
        "composer.prompt": (
            f"bold {ACCENT}"
        ),

        # Bottom hints
        "composer.hint": MUTED,
        "composer.model": SOFT,
        "composer.busy": ACCENT,

        # Help
        "help.border": DIM,
        "help.title": f"bold {TEXT}",
        "help.command": ACCENT,
        "help.description": SOFT,

        # Completion
        "completion-menu": (
            f"bg:{SURFACE_2} "
            f"{TEXT}"
        ),
        "completion-menu.completion": (
            f"bg:{SURFACE_2} "
            f"{TEXT}"
        ),
        "completion-menu.completion.current": (
            f"bg:{SURFACE_3} "
            f"{TEXT}"
        ),
        "completion-menu.meta.completion": (
            f"bg:{SURFACE_2} "
            f"{MUTED}"
        ),
        "completion-menu.meta.completion.current": (
            f"bg:{SURFACE_3} "
            f"{SOFT}"
        ),
        "completion-menu.scrollbar.background": (
            f"bg:{SURFACE_2}"
        ),
        "completion-menu.scrollbar.button": (
            f"bg:{DIM}"
        ),
    }
)


# ============================================================================
# TRANSCRIPT
# ============================================================================

@dataclass
class TranscriptItem:
    kind: str
    text: str
    status: str | None = None
    meta: str | None = None


# ============================================================================
# COMMAND COMPLETER
# ============================================================================

class IRISCommandCompleter(Completer):
    COMMANDS = [
        ("/help", "Mostra tutti i comandi"),
        ("/model", "Mostra o modifica il modello"),
        ("/model auto", "Attiva il routing automatico"),
        ("/model gemini", "Forza un provider"),
        ("/providers", "Mostra lo stato dei provider"),
        ("/status", "Mostra lo stato runtime"),
        ("/context", "Mostra token e context"),
        ("/tools", "Mostra i tool disponibili"),
        ("/memory", "Mostra lo stato della memoria"),
        ("/permissions", "Mostra i permessi attivi"),
        ("/settings", "Mostra le impostazioni"),
        ("/debug", "Attiva/disattiva debug"),
        ("/clear", "Pulisce il terminale"),
        ("/reset", "Resetta lo stato runtime"),
        ("/agent", "Avvia l'Agent Loop"),
        ("/exit", "Chiude IRIS"),
    ]

    def get_completions(
        self,
        document: Document,
        complete_event,
    ):
        text = document.text_before_cursor

        if not text.startswith("/"):
            return

        parts = text.split()
        current_word = (
            parts[-1]
            if parts
            else "/"
        )

        for command, description in self.COMMANDS:
            if command.lower().startswith(
                current_word.lower()
            ):
                yield Completion(
                    command,
                    start_position=-len(
                        current_word
                    ),
                    display=command,
                    display_meta=description,
                )


# ============================================================================
# TERMINAL UI
# ============================================================================

class TerminalUI:
    """
    UI persistente di IRIS.

    La Application viene creata UNA SOLA VOLTA e resta attiva durante
    tutta la sessione.

    Struttura:

        HEADER

        transcript
        transcript
        transcript

                    spazio libero

        ┌─────────────────────────────────────────────┐
        │ ›                                           │
        └─────────────────────────────────────────────┘

          Enter invia · Shift+Tab cambia modello
                              provider / modello
    """

    def __init__(
        self,
        event_bus: IRISEventBus,
        router,
        tool_registry,
        permission_manager,
    ) -> None:
        self.console = Console(
            color_system="truecolor",
        )

        self.state = TerminalState()

        self.router = router
        self.tool_registry = tool_registry
        self.permission_manager = permission_manager
        self.event_bus = event_bus

        self.event_bus.subscribe(
            self._on_event
        )

        self.debug_enabled = False

        self.transcript: list[
            TranscriptItem
        ] = []

        self._application: Application | None = None
        self._input_box: TextArea | None = None

        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="iris-ui",
        )

        self._busy = False
        self._help_visible = False
        self._should_exit = False

    # ========================================================================
    # START
    # ========================================================================

    def start(self) -> None:
        self.console.clear()

    # ========================================================================
    # EVENTS
    # ========================================================================

    def _on_event(self, event) -> None:
        self.state.apply(event)

        if self._application is not None:
            self._application.invalidate()

    # ========================================================================
    # MAIN SESSION
    # ========================================================================

    def run_session(
        self,
        chat_callback: Callable[[str], Any],
        agent_callback: Callable[[str], Any],
    ) -> None:
        """
        Avvia l'unica Application full-screen di IRIS.

        L'Application rimane viva mentre il Core lavora in background.
        """

        application, input_box = (
            self._build_application()
        )

        self._application = application
        self._input_box = input_box

        try:
            application.run()

        finally:
            self._application = None
            self._input_box = None

            self._executor.shutdown(
                wait=False,
                cancel_futures=False,
            )

            self.console.clear()

    # ========================================================================
    # APPLICATION
    # ========================================================================

    def _build_application(
        self,
    ) -> tuple[Application, TextArea]:
        bindings = KeyBindings()

        input_box = TextArea(
            text="",
            prompt=[
                (
                    "class:composer.prompt",
                    "    › ",
                )
            ],
            style="class:composer.input",
            multiline=False,
            wrap_lines=False,
            scrollbar=False,
            completer=IRISCommandCompleter(),
            complete_while_typing=True,
        )

        # Il composer è in fondo alla UI: il menu dei completamenti
        # deve aprirsi sopra il campo invece che sotto.
        
        # --------------------------------------------------------------------
        # ENTER
        # --------------------------------------------------------------------

        @bindings.add("enter")
        def _submit(event) -> None:
            if self._busy:
                return

            if self._help_visible:
                return

            value = (
                input_box.text.strip()
            )

            if not value:
                return

            input_box.text = ""

            self._handle_input(
                value
            )

        # --------------------------------------------------------------------
        # ESC
        # --------------------------------------------------------------------

        @bindings.add("escape")
        def _escape(event) -> None:
            if self._help_visible:
                self._help_visible = False
                event.app.invalidate()
                return

            if input_box.text:
                input_box.text = ""
                event.app.invalidate()

        # --------------------------------------------------------------------
        # CTRL+C
        # --------------------------------------------------------------------

        @bindings.add("c-c")
        def _cancel(event) -> None:
            if self._busy:
                return

            input_box.text = ""
            event.app.invalidate()

        # --------------------------------------------------------------------
        # SHIFT+TAB
        # --------------------------------------------------------------------

        @bindings.add("s-tab")
        def _toggle_model(event) -> None:
            if self._busy:
                return

            # IMPORTANTISSIMO:
            # Non aggiungiamo alcun messaggio al transcript.
            self._toggle_model_state_only()

            event.app.invalidate()

        # --------------------------------------------------------------------
        # SLASH COMPLETION
        # --------------------------------------------------------------------
        #
        # prompt_toolkit normalmente gestisce la digitazione di "/" con
        # l'inserimento standard del carattere.
        #
        # Qui intercettiamo solamente "/" per aprire immediatamente il
        # completion menu. Tutto il resto della tastiera rimane invariato.
        #

        @bindings.add("/")
        def _slash_completion(event) -> None:
            if self._busy or self._help_visible:
                return

            buffer = event.current_buffer

            buffer.insert_text("/")

            buffer.start_completion(
                select_first=False,
                complete_event=None,
            )

        # --------------------------------------------------------------------
        # HEADER
        # --------------------------------------------------------------------

        header = Window(
            content=FormattedTextControl(
                self._header_text,
            ),
            height=Dimension.exact(1),
            style="class:root",
            always_hide_cursor=True,
        )

        # --------------------------------------------------------------------
        # TRANSCRIPT
        # --------------------------------------------------------------------

        transcript = Window(
            content=FormattedTextControl(
                self._transcript_text,
            ),
            style="class:root",
            wrap_lines=True,
            always_hide_cursor=True,
            dont_extend_height=False,
        )

        # --------------------------------------------------------------------
        # COMPOSER
        # --------------------------------------------------------------------

        composer = Frame(
            input_box,
            style="class:composer",
            title="",
        )

        composer_row = VSplit(
            [
                Window(
                    width=Dimension.exact(4),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),
                composer,
                Window(
                    width=Dimension.exact(4),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),
            ]
        )

        # --------------------------------------------------------------------
        # FOOTER
        # --------------------------------------------------------------------

        footer_row = VSplit(
            [
                Window(
                    width=Dimension.exact(4),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),
                Window(
                    content=FormattedTextControl(
                        self._composer_footer_text,
                    ),
                    height=Dimension.exact(1),
                    style="class:root",
                    always_hide_cursor=True,
                ),
            ]
        )

        # --------------------------------------------------------------------
        # HELP OVERLAY
        # --------------------------------------------------------------------

        help_window = Window(
            content=FormattedTextControl(
                self._help_text,
            ),
            style="class:root",
            wrap_lines=True,
            always_hide_cursor=True,
        )

        root = HSplit(
            [
                # Top breathing room
                Window(
                    height=Dimension.exact(1),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

                # Header
                VSplit(
                    [
                        Window(
                            width=Dimension.exact(4),
                            char=" ",
                            style="class:root",
                            always_hide_cursor=True,
                        ),
                        header,
                    ]
                ),

                # Header spacing
                Window(
                    height=Dimension.exact(2),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

                # Main body
                VSplit(
                    [
                        Window(
                            width=Dimension.exact(4),
                            char=" ",
                            style="class:root",
                            always_hide_cursor=True,
                        ),
                        transcript,
                        Window(
                            width=Dimension.exact(4),
                            char=" ",
                            style="class:root",
                            always_hide_cursor=True,
                        ),
                    ]
                ),

                # Breathing room before composer
                Window(
                    height=Dimension.exact(2),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

                # Composer
                composer_row,

                # Footer
                Window(
                    height=Dimension.exact(1),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),
                footer_row,

                # Bottom breathing room
                Window(
                    height=Dimension.exact(1),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),
            ]
        )

        # Help is rendered over transcript by changing the control content.
        # We don't rebuild the application when it opens/closes.

        # --------------------------------------------------------------------
        # FLOAT CONTAINER PER IL MENU DI COMPLETAMENTO
        # --------------------------------------------------------------------
        #
        # FIX: senza un FloatContainer + CompletionsMenu, buffer.start_completion()
        # calcola le completions ma non esiste nessun elemento nel layout che
        # le disegni a schermo. Questo è il motivo per cui il menu "/" non
        # appariva mai. Il resto della UI (root) resta identico.
        #

        root_with_completion_menu = FloatContainer(
            content=root,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(
                        max_height=12,
                        scroll_offset=1,
                    ),
                ),
            ],
        )

        application = Application(
            layout=Layout(
                root_with_completion_menu,
                focused_element=input_box,
            ),
            key_bindings=bindings,
            style=PROMPT_STYLE,
            full_screen=True,
            mouse_support=False,
            erase_when_done=False,
            refresh_interval=0.2,
        )

        return application, input_box

    # ========================================================================
    # INPUT DISPATCH
    # ========================================================================

    def _handle_input(
        self,
        value: str,
    ) -> None:
        if value.startswith("/"):
            result = self._handle_command_internal(
                value
            )

            if result == "exit":
                self._should_exit = True

                if self._application is not None:
                    self._application.exit()

            return

        if self._busy:
            return

        self.transcript.append(
            TranscriptItem(
                kind="user",
                text=value,
            )
        )

        self._busy = True
        self.state.reset_runtime()

        self._invalidate()

        self._executor.submit(
            self._run_chat,
            value,
            self._application,
        )

    # ========================================================================
    # BACKGROUND CHAT
    # ========================================================================

    def _run_chat(
        self,
        message: str,
        application: Application | None,
    ) -> None:
        try:
            response = self._call_safely(
                lambda: self._active_chat_callback(
                    message
                )
            )

            self.transcript.append(
                TranscriptItem(
                    kind="iris",
                    text=str(response),
                    status="done",
                )
            )

        except Exception as error:
            self.transcript.append(
                TranscriptItem(
                    kind="iris",
                    text=(
                        "Errore: "
                        f"{error}"
                    ),
                    status="error",
                )
            )

        finally:
            self._busy = False

            if application is not None:
                application.invalidate()

    # ========================================================================
    # BACKGROUND AGENT
    # ========================================================================

    def _run_agent(
        self,
        goal: str,
        application: Application | None,
    ) -> None:
        try:
            result = self._call_safely(
                lambda: self._active_agent_callback(
                    goal
                )
            )

            message = (
                getattr(
                    result,
                    "message",
                    None,
                )
                or (
                    "Operazione completata."
                    if getattr(
                        getattr(
                            result,
                            "decision",
                            None,
                        ),
                        "value",
                        "",
                    )
                    == "done"
                    else "Operazione terminata."
                )
            )

            total_seconds = getattr(
                result,
                "total_seconds",
                0.0,
            )

            planning_seconds = getattr(
                result,
                "planning_seconds",
                0.0,
            )

            execution_seconds = getattr(
                result,
                "execution_seconds",
                0.0,
            )

            verification_seconds = getattr(
                result,
                "verification_seconds",
                0.0,
            )

            planner_calls = getattr(
                result,
                "planner_calls",
                0,
            )

            meta = (
                f"{total_seconds:.2f}s total  ·  "
                f"{planning_seconds:.2f}s planning  ·  "
                f"{execution_seconds:.2f}s tool  ·  "
                f"{verification_seconds:.2f}s verify  ·  "
                f"planner {planner_calls}"
            )

            decision = getattr(
                result,
                "decision",
                None,
            )

            decision_value = getattr(
                decision,
                "value",
                "done",
            )

            status = (
                "done"
                if decision_value == "done"
                else str(decision_value)
            )

            self.transcript.append(
                TranscriptItem(
                    kind="iris",
                    text=str(message),
                    status=status,
                    meta=meta,
                )
            )

        except Exception as error:
            self.transcript.append(
                TranscriptItem(
                    kind="iris",
                    text=(
                        "Errore Agent Loop: "
                        f"{error}"
                    ),
                    status="error",
                )
            )

        finally:
            self._busy = False

            if application is not None:
                application.invalidate()

    # ========================================================================
    # CALLBACKS
    # ========================================================================

    def set_callbacks(
        self,
        chat_callback: Callable[[str], Any],
        agent_callback: Callable[[str], Any],
    ) -> None:
        self._active_chat_callback = (
            chat_callback
        )

        self._active_agent_callback = (
            agent_callback
        )

    # ========================================================================
    # SAFE CALLBACK
    # ========================================================================

    @staticmethod
    def _call_safely(
        callback: Callable[[], Any],
    ) -> Any:
        return callback()

    # ========================================================================
    # HEADER
    # ========================================================================

    def _header_text(
        self,
    ) -> FormattedText:
        mode = (
            "FORCED"
            if self.router.forced_provider
            else "AUTO"
        )

        provider = (
            self.state.provider
            if self.state.provider != "-"
            else self._current_provider_display()
        )

        model = (
            self.state.model
            if self.state.model != "-"
            else self._current_model_display()
        )

        task = (
            self.state.task
            if self.state.task != "-"
            else "general"
        )

        mode_style = (
            "class:header.forced"
            if self.router.forced_provider
            else "class:header.muted"
        )

        busy_fragment = (
            "  ·  WORKING"
            if self._busy
            else ""
        )

        return FormattedText(
            [
                (
                    "class:header.accent",
                    "IRIS",
                ),
                (
                    "class:header.muted",
                    "  ● ONLINE",
                ),
                (
                    "class:header.muted",
                    "    ",
                ),
                (
                    "class:header",
                    task.upper(),
                ),
                (
                    "class:header.muted",
                    "    ",
                ),
                (
                    "class:header.model",
                    f"{provider} / {model}",
                ),
                (
                    "class:header.muted",
                    "    ",
                ),
                (
                    mode_style,
                    mode,
                ),
                (
                    "class:header.muted",
                    busy_fragment,
                ),
            ]
        )

    # ========================================================================
    # TRANSCRIPT
    # ========================================================================

    def _transcript_text(
        self,
    ) -> FormattedText:
        if self._help_visible:
            return self._help_text()

        fragments: list[
            tuple[str, str]
        ] = []

        items = self.transcript[-18:]

        for index, item in enumerate(items):
            if index > 0:
                fragments.append(
                    (
                        "class:root",
                        "\n\n",
                    )
                )

            if item.kind == "user":
                fragments.extend(
                    [
                        (
                            "class:user.prompt",
                            "    › ",
                        ),
                        (
                            "class:user",
                            item.text,
                        ),
                    ]
                )

            elif item.kind == "iris":
                status = (
                    item.status
                    or ""
                )

                if status == "done":
                    status_style = (
                        "class:iris.meta"
                    )
                elif status == "error":
                    status_style = (
                        "class:iris.meta"
                    )
                else:
                    status_style = (
                        "class:iris.meta"
                    )

                fragments.extend(
                    [
                        (
                            "class:iris.label",
                            "    ● IRIS",
                        ),
                        (
                            "class:root",
                            "  ",
                        ),
                        (
                            status_style,
                            status,
                        ),
                        (
                            "class:root",
                            "\n",
                        ),
                        (
                            "class:iris",
                            self._indent_text(
                                item.text,
                                6,
                            ),
                        ),
                    ]
                )

                if item.meta:
                    fragments.extend(
                        [
                            (
                                "class:root",
                                "\n",
                            ),
                            (
                                "class:iris.meta",
                                self._indent_text(
                                    item.meta,
                                    6,
                                ),
                            ),
                        ]
                    )

            elif item.kind == "system":
                fragments.extend(
                    [
                        (
                            "class:system",
                            "    · ",
                        ),
                        (
                            "class:system",
                            item.text,
                        ),
                    ]
                )

        live = self._live_activity_text()

        if live:
            if fragments:
                fragments.append(
                    (
                        "class:root",
                        "\n\n",
                    )
                )

            fragments.extend(
                live
            )

        if not fragments:
            fragments.append(
                (
                    "class:root",
                    "",
                )
            )

        return FormattedText(
            fragments
        )

    # ========================================================================
    # LIVE ACTIVITY
    # ========================================================================

    def _live_activity_text(
        self,
    ) -> list[
        tuple[str, str]
    ]:
        if not self._busy:
            return []

        activity = (
            self.state.activity
            or "IRIS sta lavorando..."
        )

        fragments = [
            (
                "class:iris.label",
                "    ● ",
            ),
            (
                "class:iris",
                activity,
            ),
        ]

        if self.state.detail:
            fragments.extend(
                [
                    (
                        "class:root",
                        "\n",
                    ),
                    (
                        "class:iris.meta",
                        self._indent_text(
                            self.state.detail,
                            6,
                        ),
                    ),
                ]
            )

        if self.state.tool_name:
            fragments.extend(
                [
                    (
                        "class:root",
                        "\n",
                    ),
                    (
                        "class:iris.meta",
                        self._indent_text(
                            (
                                self.state.tool_name
                                + "  "
                                + (
                                    self.state.tool_status
                                    or "running"
                                )
                            ),
                            6,
                        ),
                    ),
                ]
            )

        if self.state.total_steps:
            fragments.extend(
                [
                    (
                        "class:root",
                        "\n",
                    ),
                    (
                        "class:iris.meta",
                        self._indent_text(
                            self._step_text(),
                            6,
                        ),
                    ),
                ]
            )

        return fragments

    # ========================================================================
    # FOOTER
    # ========================================================================

    def _composer_footer_text(
        self,
    ) -> FormattedText:
        provider = (
            self.state.provider
            if self.state.provider != "-"
            else self._current_provider_display()
        )

        model = (
            self.state.model
            if self.state.model != "-"
            else self._current_model_display()
        )

        if self._busy:
            return FormattedText(
                [
                    (
                        "class:composer.busy",
                        "    IRIS sta lavorando...",
                    ),
                ]
            )

        return FormattedText(
            [
                (
                    "class:composer.hint",
                    "    Enter ",
                ),
                (
                    "class:composer.hint",
                    "invia",
                ),
                (
                    "class:composer.hint",
                    "    ·    ",
                ),
                (
                    "class:composer.hint",
                    "Shift+Tab ",
                ),
                (
                    "class:composer.hint",
                    "modello",
                ),
                (
                    "class:composer.hint",
                    "    ·    ",
                ),
                (
                    "class:composer.model",
                    f"{provider} / {model}",
                ),
            ]
        )

    # ========================================================================
    # HELP
    # ========================================================================

    def _help_text(
        self,
    ) -> FormattedText:
        fragments: list[
            tuple[str, str]
        ] = []

        fragments.append(
            (
                "class:help.title",
                "    COMANDI",
            )
        )

        fragments.append(
            (
                "class:root",
                "\n\n",
            )
        )

        for index, (
            command,
            description,
        ) in enumerate(
            IRISCommandCompleter.COMMANDS
        ):
            if index > 0:
                fragments.append(
                    (
                        "class:root",
                        "\n",
                    )
                )

            fragments.extend(
                [
                    (
                        "class:help.command",
                        f"    {command}",
                    ),
                    (
                        "class:help.description",
                        f"    {description}",
                    ),
                ]
            )

        fragments.extend(
            [
                (
                    "class:root",
                    "\n\n",
                ),
                (
                    "class:help.border",
                    "    ESC per chiudere",
                ),
            ]
        )

        return FormattedText(
            fragments
        )

    # ========================================================================
    # MODEL MODE
    # ========================================================================

    def _toggle_model_state_only(
        self,
    ) -> None:
        if self.router.forced_provider is None:
            available = [
                provider
                for provider
                in self.router.providers
                if getattr(
                    provider,
                    "name",
                    "",
                ) != "gemma"
            ]

            if not available:
                available = list(
                    self.router.providers
                )

            if not available:
                return

            provider = available[0]

            name = getattr(
                provider,
                "name",
                provider.__class__.__name__,
            )

            self.router.set_forced_provider(
                name
            )

        else:
            self.router.clear_forced_provider()

        # Nessun transcript.
        # Nessun messaggio.
        # Solo lo stato cambia.

    # ========================================================================
    # SLASH COMMANDS
    # ========================================================================

    def _handle_command_internal(
        self,
        raw_command: str,
    ) -> str:
        try:
            parts = shlex.split(
                raw_command
            )

        except ValueError as error:
            self._append_system(
                f"Comando non valido: {error}"
            )
            return "handled"

        if not parts:
            return "handled"

        command = parts[0].lower()

        if command in {
            "/exit",
            "/quit",
        }:
            return "exit"

        if command == "/help":
            self._help_visible = True
            self._invalidate()
            return "handled"

        if command == "/providers":
            self._show_providers()
            return "handled"

        if command == "/status":
            self._show_status()
            return "handled"

        if command == "/context":
            self._show_context()
            return "handled"

        if command == "/tools":
            self._show_tools()
            return "handled"

        if command == "/memory":
            self._show_memory()
            return "handled"

        if command == "/permissions":
            self._show_permissions()
            return "handled"

        if command == "/settings":
            self._show_settings()
            return "handled"

        if command == "/debug":
            self.debug_enabled = (
                not self.debug_enabled
            )

            self._append_system(
                (
                    "Debug ON"
                    if self.debug_enabled
                    else "Debug OFF"
                )
            )

            return "handled"

        if command == "/clear":
            self.transcript.clear()
            self.state.reset_runtime()
            self._help_visible = False
            self._invalidate()
            return "handled"

        if command == "/reset":
            self.state.reset_runtime()

            self._append_system(
                "Stato runtime resettato."
            )

            return "handled"

        if command == "/model":
            self._handle_model_command(
                parts
            )
            return "handled"

        if command == "/agent":
            goal = raw_command[
                len("/agent"):
            ].strip()

            if not goal:
                self._append_system(
                    "Specifica un obiettivo dopo /agent."
                )
                return "handled"

            self._start_agent(
                goal
            )

            return "handled"

        self._append_system(
            (
                f"Comando sconosciuto: "
                f"{command}. Usa /help."
            )
        )

        return "handled"

    # ========================================================================
    # START BACKGROUND AGENT
    # ========================================================================

    def _start_agent(
        self,
        goal: str,
    ) -> None:
        if self._busy:
            return

        self.transcript.append(
            TranscriptItem(
                kind="user",
                text=f"/agent {goal}",
            )
        )

        self._busy = True
        self.state.reset_runtime()

        self._invalidate()

        self._executor.submit(
            self._run_agent,
            goal,
            self._application,
        )

    # ========================================================================
    # SYSTEM
    # ========================================================================

    def _append_system(
        self,
        message: str,
    ) -> None:
        self.transcript.append(
            TranscriptItem(
                kind="system",
                text=message,
            )
        )

        self._invalidate()

    # ========================================================================
    # COMMAND IMPLEMENTATIONS
    # ========================================================================

    def _handle_model_command(
        self,
        parts: list[str],
    ) -> None:
        if len(parts) == 1:
            provider_name = (
                self.router.current_provider_name()
            )

            if provider_name is None:
                self._append_system(
                    "AUTO · routing automatico"
                )
                return

            provider = (
                self.router.get_provider(
                    provider_name
                )
            )

            self._append_system(
                (
                    "FORCED  "
                    f"provider={provider_name}  "
                    f"model={getattr(provider, 'model', '-')}"
                )
            )

            return

        target = parts[1]

        if target.lower() == "auto":
            self.router.clear_forced_provider()

            self._append_system(
                "Modalità modello: AUTO"
            )

            return

        if ":" in target:
            provider_name, model = (
                part.strip()
                for part
                in target.split(
                    ":",
                    1,
                )
            )

            if not provider_name or not model:
                self._append_system(
                    "Formato: /model provider:model"
                )
                return

            try:
                self.router.set_provider_model(
                    provider_name,
                    model,
                )

                self.router.set_forced_provider(
                    provider_name
                )

                self._append_system(
                    (
                        "FORCED · "
                        f"{provider_name} / {model}"
                    )
                )

            except Exception as error:
                self._append_system(
                    str(error)
                )

            return

        try:
            self.router.set_forced_provider(
                target
            )

            provider = (
                self.router.get_provider(
                    target
                )
            )

            self._append_system(
                (
                    "FORCED · "
                    f"{target} / "
                    f"{getattr(provider, 'model', '-')}"
                )
            )

        except Exception as error:
            self._append_system(
                str(error)
            )

    def _show_providers(self) -> None:
        statuses = (
            self.router.provider_status()
        )

        rows = []

        for provider in self.router.providers:
            name = getattr(
                provider,
                "name",
                provider.__class__.__name__,
            )

            rows.append(
                (
                    str(name),
                    (
                        f"{getattr(provider, 'model', '-')}"
                        f"  "
                        f"{statuses.get(str(name).lower(), 'unknown')}"
                    ),
                )
            )

        self._append_multiline_system(
            "PROVIDERS",
            rows,
        )

    def _show_status(self) -> None:
        self._append_system(
            "  ".join(
                [
                    f"provider={self.state.provider}",
                    f"model={self.state.model}",
                    f"task={self.state.task}",
                    f"phase={self.state.phase}",
                    f"tool={self.state.tool_name or '-'}",
                    (
                        "verify="
                        f"{self.state.verification_status}"
                    ),
                ]
            )
        )

    def _show_context(self) -> None:
        self._append_system(
            (
                f"input={self.state.input_tokens or '-'}  "
                f"output={self.state.output_tokens or '-'}  "
                f"total={self.state.total_tokens or '-'}  "
                f"context={self._context_text()}"
            )
        )

    def _show_tools(self) -> None:
        definitions = (
            self.tool_registry.definitions()
        )

        rows = [
            (
                str(
                    item.get(
                        "name",
                        "?",
                    )
                ),
                str(
                    item.get(
                        "description",
                        "",
                    )
                ),
            )
            for item in definitions
        ]

        self._append_multiline_system(
            "TOOLS",
            rows,
        )

    def _show_memory(self) -> None:
        self._append_system(
            (
                "memory hits="
                f"{self.state.memory_hits}  "
                "status=connected"
            )
        )

    def _show_permissions(self) -> None:
        granted = getattr(
            self.permission_manager,
            "granted",
            set(),
        )

        names = sorted(
            str(
                getattr(
                    item,
                    "value",
                    item,
                )
            )
            for item in granted
        )

        self._append_system(
            (
                "permissions="
                + (
                    ", ".join(names)
                    if names
                    else "none"
                )
            )
        )

    def _show_settings(self) -> None:
        mode = (
            "FORCED"
            if self.router.forced_provider
            else "AUTO"
        )

        self._append_system(
            (
                f"mode={mode}  "
                f"forced_provider="
                f"{self.router.forced_provider or '-'}  "
                f"debug="
                f"{'ON' if self.debug_enabled else 'OFF'}  "
                f"tools="
                f"{len(self.tool_registry.definitions())}  "
                f"providers="
                f"{len(self.router.providers)}"
            )
        )

    def _append_multiline_system(
        self,
        title: str,
        rows: list[tuple[str, str]],
    ) -> None:
        text_lines = [
            title,
            "",
        ]

        for left, right in rows:
            text_lines.append(
                f"{left}    {right}"
            )

        self._append_system(
            "\n".join(text_lines)
        )

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _invalidate(self) -> None:
        if self._application is not None:
            self._application.invalidate()

    def _step_text(self) -> str:
        if not self.state.total_steps:
            return ""

        return (
            "step "
            f"{self.state.current_step or 0}"
            "/"
            f"{self.state.total_steps}"
        )

    def _context_text(self) -> str:
        if self.state.context_tokens is None:
            return "n/d"

        if self.state.context_limit is None:
            return (
                f"{self.state.context_tokens}"
                "/n/d"
            )

        pct = (
            self.state.context_tokens
            / max(
                1,
                self.state.context_limit,
            )
        ) * 100

        return (
            f"{self.state.context_tokens}/"
            f"{self.state.context_limit} "
            f"({pct:.1f}%)"
        )

    def _current_provider_display(
        self,
    ) -> str:
        return (
            self.router.current_provider_name()
            or "-"
        )

    def _current_model_display(
        self,
    ) -> str:
        provider_name = (
            self.router.current_provider_name()
        )

        if not provider_name:
            return "-"

        try:
            provider = (
                self.router.get_provider(
                    provider_name
                )
            )

            return str(
                getattr(
                    provider,
                    "model",
                    "-",
                )
            )

        except Exception:
            return "-"

    @staticmethod
    def _indent_text(
        text: str,
        spaces: int,
    ) -> str:
        prefix = " " * spaces

        lines = text.splitlines()

        if not lines:
            return prefix

        return "\n".join(
            prefix + line
            for line in lines
        )
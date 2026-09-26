from __future__ import annotations

import shlex
import textwrap
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import RLock
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

        "header": TEXT,
        "header.accent": f"bold {ACCENT}",
        "header.muted": MUTED,
        "header.model": SOFT,
        "header.forced": ACCENT,

        "user": TEXT,
        "user.prompt": f"bold {ACCENT}",
        "iris": TEXT,
        "iris.label": f"bold {ACCENT}",
        "iris.meta": MUTED,
        "system": MUTED,

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

        "composer.hint": MUTED,
        "composer.model": SOFT,
        "composer.busy": ACCENT,

        "help.border": DIM,
        "help.title": f"bold {TEXT}",
        "help.command": ACCENT,
        "help.description": SOFT,

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

    Il transcript viene mantenuto integralmente internamente, ma il viewport
    mostra sempre la coda più recente che entra nello spazio disponibile.

    In questo modo:
    - i messaggi nuovi restano sempre visibili;
    - quelli vecchi vengono esclusi dalla visualizzazione dall'alto;
    - il transcript non viene realmente perso;
    - la UI si comporta come un log a scorrimento verso il basso.
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

        self._state_lock = RLock()

        self._application: Application | None = None
        self._input_box: TextArea | None = None

        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="iris-ui",
        )

        self._busy = False
        self._help_visible = False
        self._should_exit = False
        self._transcript_scroll_position: int | None = None

        self._active_chat_callback: Callable[
            [str],
            Any,
        ] | None = None

        self._active_agent_callback: Callable[
            [str],
            Any,
        ] | None = None

    # ========================================================================
    # START
    # ========================================================================

    def start(self) -> None:
        self.console.clear()

    # ========================================================================
    # EVENTS
    # ========================================================================

    def _on_event(self, event) -> None:
        with self._state_lock:
            self.state.apply(event)

        self._invalidate()

    # ========================================================================
    # MAIN SESSION
    # ========================================================================

    def run_session(
        self,
        chat_callback: Callable[[str], Any],
        agent_callback: Callable[[str], Any],
    ) -> None:
        self.set_callbacks(
            chat_callback=chat_callback,
            agent_callback=agent_callback,
        )

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
            get_line_prefix=self._transcript_line_prefix,
            scrollbar=False,
            completer=IRISCommandCompleter(),
            complete_while_typing=True,
        )

        @bindings.add("enter")
        def _submit(event) -> None:
            if self._busy:
                return

            if self._help_visible:
                return

            value = input_box.text.strip()

            if not value:
                return

            input_box.text = ""

            self._handle_input(
                value
            )

        @bindings.add("escape")
        def _escape(event) -> None:
            if self._help_visible:
                with self._state_lock:
                    self._help_visible = False

                event.app.invalidate()
                return

            if input_box.text:
                input_box.text = ""
                event.app.invalidate()

        @bindings.add("c-c")
        def _cancel(event) -> None:
            if self._busy:
                return

            input_box.text = ""
            event.app.invalidate()

        @bindings.add("s-tab")
        def _toggle_model(event) -> None:
            if self._busy:
                return

            self._toggle_model_state_only()

            event.app.invalidate()

        @bindings.add("pageup")
        def _transcript_page_up(event) -> None:            with self._state_lock:
                if self._transcript_scroll_position is None:
                    current = 10**9
                else:
                    current = self._transcript_scroll_position

                step = max(
                    1,
                    self._get_transcript_available_rows() - 2,
                )

                self._transcript_scroll_position = max(
                    0,
                    current - step,
                )

            event.app.invalidate()

        @bindings.add("pagedown")
        def _transcript_page_down(event) -> None:
            with self._state_lock:
                if self._transcript_scroll_position is None:
                    return

                step = max(
                    1,
                    self._get_transcript_available_rows() - 2,
                )

                self._transcript_scroll_position += step

            event.app.invalidate()

        @bindings.add("c-home")
        def _transcript_home(event) -> None:
            with self._state_lock:
                self._transcript_scroll_position = 0

            event.app.invalidate()

        @bindings.add("c-end")
        def _transcript_end(event) -> None:
            with self._state_lock:
                self._transcript_scroll_position = None

            event.app.invalidate()

        @bindings.add("/")
        def _slash_completion(event) -> None:
            if self._busy or self._help_visible:                return

            buffer = event.current_buffer

            buffer.insert_text("/")

            buffer.start_completion(
                select_first=False,
                complete_event=None,
            )

        header = Window(
            content=FormattedTextControl(
                self._header_text,
            ),
            height=Dimension.exact(1),
            style="class:root",
            always_hide_cursor=True,
        )

        transcript = Window(
            content=FormattedTextControl(
                self._transcript_text,
            ),
            style="class:root",
            wrap_lines=True,
            get_line_prefix=self._transcript_line_prefix,
            get_vertical_scroll=self._get_transcript_vertical_scroll,
            always_hide_cursor=True,
            dont_extend_height=False,
        )

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
                Window(
                    height=Dimension.exact(1),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

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

                Window(
                    height=Dimension.exact(2),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

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

                Window(
                    height=Dimension.exact(2),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

                composer_row,

                Window(
                    height=Dimension.exact(1),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),

                footer_row,

                Window(
                    height=Dimension.exact(1),
                    char=" ",
                    style="class:root",
                    always_hide_cursor=True,
                ),
            ]
        )

        # Manteniamo invariato il sistema di completamento.
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
            mouse_support=True,
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

        with self._state_lock:
            if self._busy:
                return

            self.transcript.append(
                TranscriptItem(
                    kind="user",
                    text=value,
                )
            )

            self._transcript_scroll_position = None
            self._busy = True
            self.state.reset_runtime()

        self._invalidate()

        application = self._application

        self._executor.submit(
            self._run_chat,
            value,
            application,
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
                lambda: self._active_chat_callback_or_raise(
                    message
                )
            )

            with self._state_lock:
                self.transcript.append(
                    TranscriptItem(
                        kind="iris",
                        text=str(response),
                        status="done",
                    )
                )

                self._transcript_scroll_position = None

        except Exception as error:
            with self._state_lock:
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

                self._transcript_scroll_position = None

        finally:
            with self._state_lock:
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
                lambda: self._active_agent_callback_or_raise(
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

            meta = (                f"{total_seconds:.2f}s total  ·  "
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

            with self._state_lock:
                self.transcript.append(
                    TranscriptItem(
                        kind="iris",
                        text=str(message),
                        status=status,
                        meta=meta,
                    )
                )

                self._transcript_scroll_position = None

        except Exception as error:
            with self._state_lock:
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

                self._transcript_scroll_position = None

        finally:
            with self._state_lock:
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

    def _active_chat_callback_or_raise(
        self,
        message: str,
    ) -> Any:
        callback = self._active_chat_callback

        if callback is None:
            raise RuntimeError(
                "Chat callback non configurata."
            )

        return callback(message)

    def _active_agent_callback_or_raise(
        self,
        goal: str,
    ) -> Any:
        callback = self._active_agent_callback

        if callback is None:
            raise RuntimeError(
                "Agent callback non configurata."
            )

        return callback(goal)

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
        with self._state_lock:
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

            busy = self._busy

        mode_style = (
            "class:header.forced"
            if self.router.forced_provider
            else "class:header.muted"
        )

        busy_fragment = (
            "  ·  WORKING"
            if busy
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
        with self._state_lock:
            help_visible = self._help_visible
            transcript = list(
                self.transcript
            )

        if help_visible:
            return self._help_text()

        visible_items = transcript

        fragments: list[
            tuple[str, str]
        ] = []

        for index, item in enumerate(
            visible_items
        ):
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
                            "class:iris.meta",
                            status,
                        ),
                        (
                            "class:root",
                            "\n",
                        ),
                    ]
                )

                fragments.append(
                    (
                        "class:iris",
                        self._format_wrapped_text(
                            item.text,
                            6,
                        ),
                    )
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
                                self._format_wrapped_text(
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
                            self._format_wrapped_text(
                                item.text,
                                6,
                            ),
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
    # TRANSCRIPT SCROLL
    # ========================================================================

    def _get_transcript_vertical_scroll(
        self,
        window: Window,
    ) -> int:
        with self._state_lock:
            position = self._transcript_scroll_position

        if position is None:
            # Un valore elevato viene poi limitato internamente da
            # prompt_toolkit all'ultimo offset valido: autoscroll in fondo.
            return 10**9

        return max(
            0,
            position,
        )

    # ========================================================================
    # TRANSCRIPT VIEWPORT
    # ========================================================================

    def _get_visible_transcript_items(
        self,
        transcript: list[TranscriptItem],
    ) -> list[TranscriptItem]:
        """
        Restituisce solamente la coda del transcript che entra nello
        spazio disponibile.

        Il transcript completo resta in memoria.

        Si parte dall'ultimo messaggio e si risale verso il passato:
        quando non c'è più spazio, i messaggi più vecchi vengono esclusi
        dalla visualizzazione.

        Questo crea un comportamento equivalente a un log con autoscroll.
        """

        if not transcript:
            return []

        available_rows = self._get_transcript_available_rows()
        available_width = self._get_transcript_available_width()

        selected_reversed: list[TranscriptItem] = []
        used_rows = 0

        # Il live activity occupa alcune righe quando IRIS sta lavorando.
        live_rows = (            0
            if not self._busy
            else 4
        )

        usable_rows = max(
            3,
            available_rows - live_rows,
        )

        for item in reversed(
            transcript
        ):
            item_rows = (
                self._estimate_transcript_item_rows(
                    item=item,
                    width=available_width,
                )
            )

            separator_rows = (
                2
                if selected_reversed
                else 0
            )

            required_rows = (
                item_rows
                + separator_rows
            )

            if (
                selected_reversed
                and used_rows + required_rows > usable_rows
            ):
                break

            # Se un singolo messaggio è più grande dell'intero viewport,
            # lo manteniamo comunque: il wrapping mostrerà almeno la parte
            # finale disponibile del contenuto.
            if (
                not selected_reversed
                and item_rows > usable_rows
            ):
                selected_reversed.append(
                    item
                )
                break

            selected_reversed.append(
                item
            )

            used_rows += required_rows

            if used_rows >= usable_rows:
                break

        selected_reversed.reverse()

        return selected_reversed

    def _get_transcript_available_rows(
        self,
    ) -> int:
        """
        Stima l'altezza reale disponibile alla zona transcript.

        Il layout contiene header, spaziatori, composer e footer fissi.
        Il transcript occupa il restante spazio.
        """

        application = self._application

        if application is None:
            return 12

        try:
            output = application.output            size = output.get_size()

            total_rows = int(
                size.rows
            )

            # Componenti verticali fissi del layout:
            #
            # 1  top spacer
            # 1  header
            # 2  header spacer
            # 2  transcript outer spacing
            # 2  bottom transcript spacer
            # 1  footer top spacer
            # 1  footer
            # 1  footer bottom spacer
            #
            # Il composer occupa almeno circa 3 righe a seconda della
            # dimensione del terminale.
            fixed_rows = 12

            rows = (
                total_rows
                - fixed_rows
            )

            return max(
                3,
                rows,
            )

        except Exception:
            return 12

    def _get_transcript_available_width(
        self,
    ) -> int:
        application = self._application

        if application is None:
            return 80

        try:
            output = application.output
            size = output.get_size()

            total_columns = int(
                size.columns
            )

            # Margini laterali del transcript.
            width = (
                total_columns
                - 8
            )

            return max(
                24,
                width,
            )

        except Exception:
            return 80

    @classmethod
    def _estimate_transcript_item_rows(
        cls,
        item: TranscriptItem,
        width: int,
    ) -> int:
        """
        Stima quante righe visive occupa un elemento del transcript.

        La stima considera:
        - indentazione;
        - wrapping;
        - status;
        - meta;
        - righe vuote interne.
        """

        width = max(
            20,
            width,
        )

        if item.kind == "user":
            content_width = max(
                12,
                width - 6,
            )

            return (
                1
                + cls._wrapped_line_count(
                    item.text,
                    content_width,
                )
                - 1
            )

        if item.kind == "iris":
            text_width = max(
                12,
                width - 6,
            )

            rows = 2

            rows += cls._wrapped_line_count(
                item.text,
                text_width,
            )

            if item.meta:
                rows += 1

                rows += cls._wrapped_line_count(
                    item.meta,
                    text_width,
                )

            return rows

        if item.kind == "system":
            text_width = max(
                12,
                width - 6,
            )

            return (
                cls._wrapped_line_count(
                    item.text,
                    text_width,
                )
                + 1
            )

        return max(
            1,
            cls._wrapped_line_count(
                item.text,
                max(
                    12,
                    width - 4,
                ),
            ),
        )

    @staticmethod
    def _wrapped_line_count(
        text: str,
        width: int,
    ) -> int:
        """
        Conta quante righe occuperà un testo dopo il wrapping.

        Le newline vengono mantenute.
        """

        if not text:
            return 1

        width = max(
            1,
            width,
        )

        total = 0

        for line in str(text).splitlines() or [""]:
            if not line:
                total += 1
                continue

            wrapped = textwrap.wrap(
                line,
                width=width,
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            )

            total += max(
                1,
                len(wrapped),
            )

        return max(
            1,
            total,
        )

    # ========================================================================
    # LIVE ACTIVITY
    # ========================================================================

    def _live_activity_text(
        self,
    ) -> list[
        tuple[str, str]
    ]:
        with self._state_lock:
            if not self._busy:
                return []

            activity = (
                self.state.activity
                or "IRIS sta lavorando..."
            )

            detail = self.state.detail
            tool_name = self.state.tool_name
            tool_status = self.state.tool_status
            total_steps = self.state.total_steps

            current_step = self.state.current_step

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

        if detail:
            fragments.extend(
                [
                    (
                        "class:root",
                        "\n",
                    ),
                    (
                        "class:iris.meta",
                        self._format_wrapped_text(
                            detail,
                            6,
                        ),
                    ),
                ]
            )

        if tool_name:
            fragments.extend(
                [
                    (
                        "class:root",
                        "\n",
                    ),
                    (
                        "class:iris.meta",
                        self._format_wrapped_text(
                            (
                                tool_name
                                + "  "
                                + (
                                    tool_status
                                    or "running"
                                )
                            ),
                            6,
                        ),
                    ),
                ]
            )

        if total_steps:
            fragments.extend(
                [
                    (
                        "class:root",
                        "\n",
                    ),
                    (
                        "class:iris.meta",
                        self._format_wrapped_text(
                            self._step_text_from_values(
                                current_step=current_step,
                                total_steps=total_steps,
                            ),
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
        with self._state_lock:
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

            busy = self._busy

        if busy:
            return FormattedText(
                [
                    (
                        "class:composer.busy",
                        "    IRIS sta lavorando...",
                    ),                ]
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
                    (                        "class:help.command",
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
        with self._state_lock:
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

    # ========================================================================
    # SLASH COMMANDS
    # ========================================================================

    def _handle_command_internal(
        self,
        raw_command: str,
    ) -> str:
        # /agent contiene testo libero: non deve essere passato a
        # shlex.split(), altrimenti apostrofi come quello di "l'alto"
        # vengono interpretati come virgolette aperte.
        if raw_command.lower().startswith(
            "/agent"
        ):
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
            with self._state_lock:
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
            with self._state_lock:
                self.debug_enabled = (
                    not self.debug_enabled
                )

                enabled = self.debug_enabled

            self._append_system(
                (
                    "Debug ON"
                    if enabled
                    else "Debug OFF"
                )
            )

            return "handled"

        if command == "/clear":
            with self._state_lock:
                self.transcript.clear()
                self.state.reset_runtime()
                self._help_visible = False
                self._transcript_scroll_position = None

            self._invalidate()
            return "handled"

        if command == "/reset":
            with self._state_lock:
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
        with self._state_lock:
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

        application = self._application

        self._executor.submit(
            self._run_agent,
            goal,
            application,
        )

    # ========================================================================
    # SYSTEM
    # ========================================================================

    def _append_system(
        self,
        message: str,
    ) -> None:
        with self._state_lock:
            self.transcript.append(
                TranscriptItem(
                    kind="system",
                    text=message,
                )
            )

            self._transcript_scroll_position = None

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
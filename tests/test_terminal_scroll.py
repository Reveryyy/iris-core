from threading import RLock

from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType

from app.ui.terminal import TerminalUI, TranscriptItem, TranscriptTextControl


def _make_terminal() -> TerminalUI:
    terminal = TerminalUI.__new__(TerminalUI)

    terminal._state_lock = RLock()
    terminal.transcript = [
        TranscriptItem(
            kind="iris",
            text="messaggio " * 20,
            status="done",
        )
        for _ in range(20)
    ]
    terminal._busy = False
    terminal._application = None
    terminal._live_activity_text = lambda: []
    terminal._invalidate = lambda: None

    return terminal


def test_transcript_renders_complete_history():
    terminal = _make_terminal()

    rendered = terminal._transcript_text()

    plain = "".join(
        fragment[1]
        for fragment in rendered
    )

    assert "messaggio" in plain
    assert len(plain) > 100


def test_transcript_max_scroll_is_positive_for_long_history():
    terminal = _make_terminal()

    assert terminal._get_transcript_max_scroll() > 0


def test_transcript_cursor_follows_bottom_when_not_manually_scrolled():
    terminal = _make_terminal()

    control = TranscriptTextControl(
        terminal,
        terminal._transcript_text,
    )

    content = control.create_content(
        width=80,
        height=12,
    )

    assert content.cursor_position.y == content.line_count - 1


def test_transcript_cursor_tracks_manual_scroll_position():
    terminal = _make_terminal()
    terminal._transcript_scroll_position = 5

    control = TranscriptTextControl(
        terminal,
        terminal._transcript_text,
    )

    content = control.create_content(
        width=80,
        height=12,
    )

    assert content.cursor_position.y >= 5


def test_transcript_mouse_scroll_up_enters_manual_mode():
    terminal = _make_terminal()

    control = TranscriptTextControl(
        terminal,
        terminal._transcript_text,
    )

    event = MouseEvent(
        position=Point(x=1, y=1),
        event_type=MouseEventType.SCROLL_UP,
        button=MouseButton.NONE,
        modifiers=frozenset(),
    )

    control.mouse_handler(event)

    assert terminal._transcript_scroll_position is not None
    assert (
        terminal._transcript_scroll_position
        < terminal._get_transcript_max_scroll()
    )


def test_transcript_mouse_scroll_down_moves_toward_bottom():
    terminal = _make_terminal()
    terminal._transcript_scroll_position = 0

    control = TranscriptTextControl(
        terminal,
        terminal._transcript_text,
    )

    event = MouseEvent(
        position=Point(x=1, y=1),
        event_type=MouseEventType.SCROLL_DOWN,
        button=MouseButton.NONE,
        modifiers=frozenset(),
    )

    control.mouse_handler(event)

    assert terminal._transcript_scroll_position == 3


def test_transcript_new_message_resets_to_follow_bottom():
    terminal = _make_terminal()
    terminal._transcript_scroll_position = 0

    terminal._append_system(
        "nuovo messaggio"
    )

    assert terminal._transcript_scroll_position is None

from threading import RLock

from app.ui.terminal import TerminalUI, TranscriptItem


def test_terminal_copies_transcript_to_windows_clipboard(monkeypatch):
    terminal = TerminalUI.__new__(TerminalUI)

    terminal._state_lock = RLock()
    terminal.transcript = [
        TranscriptItem(
            kind="user",
            text="ciao IRIS",
        ),
        TranscriptItem(
            kind="iris",
            text="Risposta di IRIS",
            status="done",
            meta="step 1/1",
        ),
        TranscriptItem(
            kind="system",
            text="Test completato.",
        ),
    ]
    terminal._append_system = lambda message: None

    copied = []

    monkeypatch.setattr(
        "app.ui.terminal.os.name",
        "nt",
    )
    monkeypatch.setattr(
        terminal,
        "_copy_windows_unicode_clipboard",
        lambda text: copied.append(text),
    )

    terminal._copy_transcript_to_clipboard()

    assert copied == [
        "› ciao IRIS\n\n"
        "IRIS [done]\n"
        "Risposta di IRIS\n"
        "step 1/1\n\n"
        "· Test completato."
    ]

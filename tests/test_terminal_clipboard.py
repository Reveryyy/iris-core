from threading import RLock
from types import SimpleNamespace

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

    captured = SimpleNamespace(
        input=None,
        args=None,
        kwargs=None,
    )

    def fake_run(args, input, text, check, creationflags):
        captured.input = input
        captured.args = args
        captured.kwargs = {
            "text": text,
            "check": check,
            "creationflags": creationflags,
        }

    monkeypatch.setattr(
        "app.ui.terminal.subprocess.run",
        fake_run,
    )

    terminal._copy_transcript_to_clipboard()

    assert captured.args == ["clip"]
    assert captured.kwargs["text"] is True
    assert captured.kwargs["check"] is True
    assert captured.input == (
        "› ciao IRIS\n\n"
        "IRIS [done]\n"
        "Risposta di IRIS\n"
        "step 1/1\n\n"
        "· Test completato."
    )

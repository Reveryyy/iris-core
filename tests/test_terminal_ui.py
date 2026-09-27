from threading import RLock

from app.agent.loop import AgentLoop
from app.ui.terminal import TerminalUI, TranscriptItem


def test_agent_output_formatter_exposes_file_content():
    output = {
        "path": r"C:\temp\test.txt",
        "content": "prima riga\nseconda riga",
        "bytes": 23,
        "user_message": "Ho letto il file 'test.txt'.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "prima riga" in rendered
    assert "seconda riga" in rendered
    assert "Ho letto il file" not in rendered


def test_agent_output_formatter_exposes_directory_entries():
    output = {
        "path": r"C:\temp",
        "entries": [
            {
                "name": "test.txt",
                "type": "file",
            },
            {
                "name": "cartella",
                "type": "directory",
            },
        ],
        "count": 2,
        "user_message": "Ho trovato 2 elementi in 'C:\\temp'.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "test.txt" in rendered
    assert "cartella" in rendered


def test_agent_output_formatter_exposes_search_results():
    output = {
        "results": [
            {
                "path": r"C:\temp\test_file.txt",
                "name": "test_file.txt",
            }
        ],
        "count": 1,
        "user_message": "Ho trovato 1 risultati.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "test_file.txt" in rendered


def test_agent_output_formatter_exposes_command_stdout():
    output = {
        "command": "echo ciao",
        "stdout": "ciao",
        "stderr": "",
        "returncode": 0,
        "user_message": "Ho eseguito il comando 'echo ciao'.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "ciao" in rendered


def test_terminal_renders_the_complete_transcript():
    terminal = TerminalUI.__new__(TerminalUI)

    terminal._state_lock = RLock()
    terminal._help_visible = False
    terminal.transcript = [
        TranscriptItem(
            kind="user",
            text="messaggio molto vecchio",
        ),
        TranscriptItem(
            kind="iris",
            text="risposta vecchia",
            status="done",
        ),
        TranscriptItem(
            kind="user",
            text="messaggio recente",
        ),
        TranscriptItem(
            kind="iris",
            text="risposta recente",
            status="done",
        ),
    ]

    terminal._live_activity_text = lambda: []

    rendered = terminal._transcript_text()
    plain = "".join(
        fragment[1]
        for fragment in rendered
    )

    assert "messaggio molto vecchio" in plain
    assert "risposta vecchia" in plain
    assert "messaggio recente" in plain
    assert "risposta recente" in plain


def test_terminal_transcript_scroll_defaults_to_following_the_bottom():
    terminal = TerminalUI.__new__(TerminalUI)

    terminal._state_lock = RLock()
    terminal._transcript_scroll_position = None

    assert (
        terminal._get_transcript_vertical_scroll(
            None
        )
        == 10**9
    )


def test_terminal_transcript_scroll_can_be_positioned_manually():
    terminal = TerminalUI.__new__(TerminalUI)

    terminal._state_lock = RLock()
    terminal._transcript_scroll_position = 17

    assert (
        terminal._get_transcript_vertical_scroll(
            None
        )
        == 17
    )


def test_agent_output_formatter_exposes_discovered_applications():
    output = {
        "count": 1,
        "applications": [
            {
                "name": "Blocco Note",
                "target": r"C:\\Windows\\notepad.exe",
                "source": "start_menu",
            }
        ],
        "user_message": "Ho scoperto 1 applicazioni disponibili sul PC.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "Blocco Note" in rendered
    assert "notepad.exe" in rendered


def test_terminal_copy_preserves_unicode_text_on_windows(
    monkeypatch,
):
    terminal = TerminalUI.__new__(TerminalUI)

    terminal._state_lock = RLock()
    terminal.transcript = [
        TranscriptItem(
            kind="iris",
            text="Risposta con freccia → e carattere ✓",
            status="done",
        ),
    ]
    terminal._append_system = lambda message: None

    copied = []

    monkeypatch.setattr(
        terminal,
        "_copy_windows_unicode_clipboard",
        lambda text: copied.append(text),
    )

    terminal._copy_transcript_to_clipboard()

    assert len(copied) == 1
    assert "→" in copied[0]
    assert "✓" in copied[0]


def test_agent_output_formatter_renders_application_windows_without_json():
    output = {
        "count": 4,
        "windows": [
            {
                "title": "Google Chrome",
                "foreground": True,
                "minimized": False,
            },
            {
                "title": "",
                "foreground": False,
                "minimized": False,
            },
            {
                "title": "Telegram",
                "foreground": False,
                "minimized": False,
            },
            {
                "title": "Visual Studio Code",
                "foreground": False,
                "minimized": True,
            },
        ],
        "user_message": "Ho rilevato 4 finestre visibili sul desktop.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "Google Chrome" in rendered
    assert "Telegram" in rendered
    assert "Visual Studio Code" in rendered
    assert '"hwnd"' not in rendered
    assert '"windows"' not in rendered


def test_agent_output_formatter_renders_processes_without_json():
    output = {
        "count": 5,
        "processes": [
            {"pid": 1, "name": "chrome", "executable": None},
            {"pid": 2, "name": "chrome", "executable": None},
            {"pid": 3, "name": "Telegram", "executable": None},
            {"pid": 4, "name": "python", "executable": None},
            {"pid": 5, "name": "python", "executable": None},
        ],
        "user_message": "Ho rilevato 5 processi attualmente in esecuzione.",
    }

    rendered = AgentLoop._format_tool_output_for_user(
        output
    )

    assert rendered is not None
    assert "5 processi" in rendered
    assert "chrome (2 istanze)" in rendered
    assert "Telegram" in rendered
    assert '"pid"' not in rendered
    assert '"processes"' not in rendered

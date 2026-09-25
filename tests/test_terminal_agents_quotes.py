from __future__ import annotations

from types import MethodType

from app.ui.terminal import TerminalUI


def test_agent_preserves_apostrophe_in_goal() -> None:
    ui = TerminalUI.__new__(
        TerminalUI
    )

    captured = []

    ui._start_agent = MethodType(
        lambda self, goal: captured.append(goal),
        ui,
    )

    result = ui._handle_command_internal(
        "/agent scorri verso l'alto"
    )

    assert result == "handled"

    assert captured == [
        "scorri verso l'alto",
    ]


def test_agent_preserves_quotes_in_goal() -> None:
    ui = TerminalUI.__new__(
        TerminalUI
    )

    captured = []

    ui._start_agent = MethodType(
        lambda self, goal: captured.append(goal),
        ui,
    )

    result = ui._handle_command_internal(
        '/agent scrivi "Ciao, Valerio"'
    )

    assert result == "handled"

    assert captured == [
        'scrivi "Ciao, Valerio"',
    ]


def test_agent_without_goal_is_rejected() -> None:
    ui = TerminalUI.__new__(
        TerminalUI
    )

    messages = []

    ui._append_system = MethodType(
        lambda self, message: messages.append(message),
        ui,
    )

    result = ui._handle_command_internal(
        "/agent"
    )

    assert result == "handled"

    assert messages == [
        "Specifica un obiettivo dopo /agent."
    ]
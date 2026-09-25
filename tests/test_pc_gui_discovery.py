from __future__ import annotations

import ctypes

from app.tools.pc_mouse import MoveMouseTool
from app.tools.pc_window_discovery import ListWindowsTool


class FakeFunction:
    def __init__(self, value=None):
        self.value = value

    def __call__(self, *args):
        if callable(self.value):
            return self.value(*args)
        return self.value


class FakeUser32ForMouse:
    def __init__(self):
        self.GetSystemMetrics = FakeFunction(
            lambda index: 1920 if index == 0 else 1080
        )
        self.SetCursorPos = FakeFunction(True)

        def get_cursor_pos(pointer):
            pointer.contents.x = 100
            pointer.contents.y = 200
            return True

        self.GetCursorPos = FakeFunction(get_cursor_pos)


class FakeUser32ForWindows:
    def __init__(self):
        self.GetForegroundWindow = FakeFunction(2)
        self.IsWindowVisible = FakeFunction(True)
        self.IsIconic = FakeFunction(False)
        self.GetWindowTextLengthW = FakeFunction(
            lambda hwnd: 7
        )
        self.GetWindowTextW = FakeFunction(
            lambda hwnd, buffer, length: setattr(
                buffer,
                "value",
                "Notepad",
            ) or 7
        )
        self.GetClassNameW = FakeFunction(
            lambda hwnd, buffer, length: setattr(
                buffer,
                "value",
                "NotepadClass",
            ) or 11
        )
        self.GetWindowThreadProcessId = FakeFunction(
            lambda hwnd, pointer: setattr(
                pointer.contents,
                "value",
                123,
            ) or 1
        )
        self.EnumWindows = FakeFunction(
            lambda callback, lparam: (
                callback(2, lparam)
                and True
            )
        )


def test_move_mouse_definition() -> None:
    definition = MoveMouseTool().definition

    assert definition.name == "move_mouse"
    assert definition.input_schema["required"] == ["x", "y"]


def test_move_mouse_rejects_coordinates_outside_screen(monkeypatch) -> None:
    monkeypatch.setattr(
        ctypes,
        "windll",
        type("FakeWindll", (), {
            "user32": FakeUser32ForMouse(),
        })(),
        raising=False,
    )

    result = MoveMouseTool().execute(
        {
            "x": 1920,
            "y": 200,
        }
    )

    assert result.success is False
    assert "fuori dallo schermo" in result.error.lower()


def test_list_windows_definition() -> None:
    definition = ListWindowsTool().definition

    assert definition.name == "list_windows"
    assert definition.input_schema["required"] == []


def test_list_windows_requires_windows(monkeypatch) -> None:
    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )

    result = ListWindowsTool().execute({})

    assert result.success is False
    assert "solo su windows" in result.error.lower()

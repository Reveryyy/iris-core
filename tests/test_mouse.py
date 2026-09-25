from __future__ import annotations

import ctypes

from app.tools.pc_mouse import (
    ClickMouseTool,
    MoveMouseTool,
)


class FakeUser32:
    def __init__(
        self,
        cursor_x: int = 0,
        cursor_y: int = 0,
    ):
        self.cursor_x = cursor_x
        self.cursor_y = cursor_y
        self.set_cursor_calls = []
        self.mouse_event_calls = []

    def GetSystemMetrics(self, index):
        values = {
            76: -1920,
            77: 0,
            78: 3840,
            79: 1080,
        }

        return values[index]

    def SetCursorPos(self, x, y):
        self.set_cursor_calls.append(
            (
                x,
                y,
            )
        )

        self.cursor_x = x
        self.cursor_y = y

        return True

    def GetCursorPos(self, pointer):
        point = pointer._obj
        point.x = self.cursor_x
        point.y = self.cursor_y
        return True

    def mouse_event(
        self,
        flags,
        dx,
        dy,
        data,
        extra_info,
    ):
        self.mouse_event_calls.append(
            (
                flags,
                dx,
                dy,
                data,
                extra_info,
            )
        )


def install_fake_user32(
    monkeypatch,
    user32,
) -> None:
    monkeypatch.setattr(
        ctypes,
        "windll",
        type(
            "FakeWindll",
            (),
            {
                "user32": user32,
            },
        )(),
        raising=False,
    )


def test_click_mouse_definition_uses_unbounded_coordinate_schema() -> None:
    definition = ClickMouseTool().definition

    assert definition.name == "click_mouse"

    properties = definition.input_schema["properties"]

    assert "minimum" not in properties["x"]
    assert "minimum" not in properties["y"]


def test_click_mouse_accepts_negative_virtual_desktop_coordinates(
    monkeypatch,
) -> None:
    user32 = FakeUser32()

    install_fake_user32(
        monkeypatch,
        user32,
    )

    result = ClickMouseTool().execute(
        {
            "x": -100,
            "y": 200,
        }
    )

    assert result.success is True

    assert user32.set_cursor_calls == [
        (
            -100,
            200,
        )
    ]

    assert result.output["virtual_screen"] == {
        "left": -1920,
        "top": 0,
        "width": 3840,
        "height": 1080,
    }


def test_click_mouse_rejects_coordinate_outside_virtual_desktop(
    monkeypatch,
) -> None:
    user32 = FakeUser32()

    install_fake_user32(
        monkeypatch,
        user32,
    )

    result = ClickMouseTool().execute(
        {
            "x": 1920,
            "y": 200,
        }
    )

    assert result.success is False
    assert "fuori" in result.error.lower()


def test_move_mouse_definition_uses_unbounded_coordinate_schema() -> None:
    definition = MoveMouseTool().definition

    properties = definition.input_schema["properties"]

    assert "minimum" not in properties["x"]
    assert "minimum" not in properties["y"]


def test_move_mouse_verifies_negative_virtual_desktop_coordinate(
    monkeypatch,
) -> None:
    user32 = FakeUser32()

    install_fake_user32(
        monkeypatch,
        user32,
    )

    result = MoveMouseTool().execute(
        {
            "x": -100,
            "y": 200,
        }
    )

    assert result.success is True

    assert result.output["verified"] is True

    assert user32.set_cursor_calls == [
        (
            -100,
            200,
        )
    ]


def test_move_mouse_requires_windows(monkeypatch) -> None:
    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )

    result = MoveMouseTool().execute(
        {
            "x": 100,
            "y": 200,
        }
    )

    assert result.success is False
    assert "solo su windows" in result.error.lower()

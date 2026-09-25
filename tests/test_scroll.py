from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.tools.pc_scroll as pc_scroll
from app.tools.pc_scroll import (
    MOUSEEVENTF_WHEEL,
    WHEEL_DELTA,
    ScrollMouseTool,
)
from app.tools.permissions import Permission


class FakeMouseEvent:
    def __init__(self) -> None:
        self.calls = []

        self.argtypes = None
        self.restype = None

    def __call__(
        self,
        flags,
        dx,
        dy,
        data,
        extra_info,
    ):
        self.calls.append(
            (
                flags,
                dx,
                dy,
                data,
                extra_info,
            )
        )


class FakeUser32:
    def __init__(self) -> None:
        self.mouse_event = FakeMouseEvent()


def install_fake_windows(
    monkeypatch,
    user32,
) -> None:
    monkeypatch.setattr(
        pc_scroll.ctypes,
        "windll",
        SimpleNamespace(
            user32=user32,
        ),
        raising=False,
    )


def remove_windows_api(
    monkeypatch,
) -> None:
    monkeypatch.delattr(
        pc_scroll.ctypes,
        "windll",
        raising=False,
    )


def test_scroll_definition() -> None:
    tool = ScrollMouseTool()

    definition = tool.definition

    assert definition.name == "scroll_mouse"

    assert "scroll" in (
        definition.description.lower()
    )

    assert definition.input_schema["type"] == "object"

    assert definition.input_schema["required"] == [
        "notches",
    ]

    assert (
        definition.input_schema["additionalProperties"]
        is False
    )

    assert definition.permissions == frozenset(
        {
            Permission.GUI.value,
        }
    )


def test_scroll_definition_limits() -> None:
    tool = ScrollMouseTool()

    properties = tool.definition.input_schema[
        "properties"
    ]

    assert properties["notches"]["minimum"] == -20
    assert properties["notches"]["maximum"] == 20


def test_scroll_rejects_missing_notches() -> None:
    tool = ScrollMouseTool()

    result = tool.execute(
        {}
    )

    assert result.success is False
    assert "intero" in result.error.lower()


def test_scroll_rejects_non_integer_notches() -> None:
    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": "5",
        }
    )

    assert result.success is False
    assert "intero" in result.error.lower()


def test_scroll_rejects_boolean_notches() -> None:
    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": True,
        }
    )

    assert result.success is False
    assert "intero" in result.error.lower()


def test_scroll_rejects_zero() -> None:
    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": 0,
        }
    )

    assert result.success is False
    assert "zero" in result.error.lower()


def test_scroll_rejects_value_below_minimum() -> None:
    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": -21,
        }
    )

    assert result.success is False
    assert "compreso" in result.error.lower()


def test_scroll_rejects_value_above_maximum() -> None:
    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": 21,
        }
    )

    assert result.success is False
    assert "compreso" in result.error.lower()


def test_scroll_requires_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remove_windows_api(
        monkeypatch
    )

    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": 1,
        }
    )

    assert result.success is False

    assert "solo su windows" in (
        result.error.lower()
    )


def test_scrolls_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": 3,
        }
    )

    assert result.success is True

    assert result.output == {
        "notches": 3,
        "direction": "up",
        "wheel_delta": 3 * WHEEL_DELTA,
    }

    assert user32.mouse_event.calls == [
        (
            MOUSEEVENTF_WHEEL,
            0,
            0,
            3 * WHEEL_DELTA,
            0,
        )
    ]


def test_scrolls_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": -4,
        }
    )

    assert result.success is True

    assert result.output == {
        "notches": -4,
        "direction": "down",
        "wheel_delta": -4 * WHEEL_DELTA,
    }

    assert user32.mouse_event.calls == [
        (
            MOUSEEVENTF_WHEEL,
            0,
            0,
            (-4 * WHEEL_DELTA) & 0xFFFFFFFF,
            0,
        )
    ]


def test_scroll_single_up_notch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": 1,
        }
    )

    assert result.success is True

    assert result.output == {
        "notches": 1,
        "direction": "up",
        "wheel_delta": WHEEL_DELTA,
    }

    assert user32.mouse_event.calls == [
        (
            MOUSEEVENTF_WHEEL,
            0,
            0,
            WHEEL_DELTA,
            0,
        )
    ]


def test_scroll_single_down_notch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    tool = ScrollMouseTool()

    result = tool.execute(
        {
            "notches": -1,
        }
    )

    assert result.success is True

    assert result.output == {
        "notches": -1,
        "direction": "down",
        "wheel_delta": -WHEEL_DELTA,
    }

    assert user32.mouse_event.calls == [
        (
            MOUSEEVENTF_WHEEL,
            0,
            0,
            (-WHEEL_DELTA) & 0xFFFFFFFF,
            0,
        )
    ]


def test_scroll_custom_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()

    install_fake_windows(
        monkeypatch,
        user32,
    )

    tool = ScrollMouseTool(
        min_notches=-2,
        max_notches=2,
    )

    result = tool.execute(
        {
            "notches": 2,
        }
    )

    assert result.success is True

    result = tool.execute(
        {
            "notches": -2,
        }
    )

    assert result.success is True

    result = tool.execute(
        {
            "notches": 3,
        }
    )

    assert result.success is False


def test_scroll_constructor_rejects_invalid_minimum() -> None:
    with pytest.raises(
        TypeError
    ):
        ScrollMouseTool(
            min_notches="x",  # type: ignore[arg-type]
        )


def test_scroll_constructor_rejects_invalid_maximum() -> None:
    with pytest.raises(
        TypeError
    ):
        ScrollMouseTool(
            max_notches="x",  # type: ignore[arg-type]
        )


def test_scroll_constructor_rejects_invalid_range() -> None:
    with pytest.raises(
        ValueError
    ):
        ScrollMouseTool(
            min_notches=5,
            max_notches=5,
        )


def test_scroll_constructor_rejects_reversed_range() -> None:
    with pytest.raises(
        ValueError
    ):
        ScrollMouseTool(
            min_notches=5,
            max_notches=-5,
        )
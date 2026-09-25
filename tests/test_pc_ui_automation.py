from __future__ import annotations

import ctypes

from app.tools.pc_ui import ListUIElementsTool


def test_list_ui_elements_definition() -> None:
    definition = ListUIElementsTool().definition

    assert definition.name == "list_ui_elements"
    assert "window_title" in definition.input_schema["properties"]
    assert definition.input_schema["required"] == ["window_title"]


def test_list_ui_elements_requires_windows(monkeypatch) -> None:
    monkeypatch.delattr(
        ctypes,
        "windll",
        raising=False,
    )

    result = ListUIElementsTool().execute(
        {
            "window_title": "Notepad",
        }
    )

    assert result.success is False
    assert "solo su windows" in result.error.lower()


def test_list_ui_elements_rejects_empty_window_title() -> None:
    result = ListUIElementsTool().execute(
        {
            "window_title": "   ",
        }
    )

    assert result.success is False
    assert "non può essere vuoto" in result.error.lower()
